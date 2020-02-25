package garage.messaging;

import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import com.google.common.util.concurrent.AbstractExecutionThreadService;
import com.google.common.util.concurrent.MoreExecutors;
import com.google.common.util.concurrent.Service;
import com.google.common.util.concurrent.ServiceManager;
import dagger.BindsInstance;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Nonnull;
import javax.inject.Inject;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import nanomsg.Message;
import nanomsg.Socket;

import garage.base.Configuration;
import garage.base.Configuration.Node;

import static nanomsg.Domain.AF_SP;
import static nanomsg.Domain.AF_SP_RAW;
import static nanomsg.Protocol.NN_REP;
import static nanomsg.Protocol.NN_REQ;

public class SimpleService {

    private static final Logger LOG =
        LoggerFactory.getLogger(SimpleService.class);

    public interface DaggerBuilderMixin<T> {
        @BindsInstance
        T simpleServiceConfig(@Node(SimpleService.class) Configuration config);
    }

    public interface Handler {
        ByteBuffer handle(ByteBuffer request) throws Exception;
    }

    private static final String DEFAULT_ROUTER_NAME = "router";
    private static final String DEFAULT_ROUTER_ADDRESS = "inproc://router";

    private static final String DEFAULT_HANDLER_NAME_FORMAT = "server-%02d";
    private static final long DEFAULT_GRACE_PERIOD = 5L;  // Unit: second.

    private final String name;

    private ServiceManager manager;

    private final String serverNameFormat;
    private final ImmutableSet<String> serverAddresses;

    private final String routerName;
    private final String routerAddress;

    private final long gracePeriod;

    @Inject
    public SimpleService(@Node(SimpleService.class) Configuration config) {
        this(
            config.getOrThrow("service_name", String.class),

            config.get("router_name", String.class)
                .orElse(DEFAULT_ROUTER_NAME),
            config.get("router_address", String.class)
                .orElse(DEFAULT_ROUTER_ADDRESS),

            config.get("server_name_format", String.class)
                .orElse(DEFAULT_HANDLER_NAME_FORMAT),
            config.getOrThrow("server_addresses", List.class),

            config.get("grace_period", Long.class)
                .orElse(DEFAULT_GRACE_PERIOD)
        );
    }

    public SimpleService(
        String name,
        String routerName,
        String routerAddress,
        String serverNameFormat,
        List<String> serverAddresses,
        long gracePeriod
    ) {
        this.name = name;

        this.manager = null;

        this.routerName = routerName;
        this.routerAddress = routerAddress;

        this.serverNameFormat = serverNameFormat;
        this.serverAddresses = ImmutableSet.copyOf(serverAddresses);

        this.gracePeriod = gracePeriod;
    }

    public void start(Iterable<? extends Handler> handlers) {
        Preconditions.checkState(manager == null);

        manager = new ServiceManager(makeServices(
            ImmutableList.copyOf(handlers)
        ));

        manager.addListener(
            new ServiceManager.Listener() {

                @Override
                public void healthy() {
                    LOG.info("{}: start serving requests", name);
                    // What else should we do here?
                }

                @Override
                public void failure(@Nonnull Service service) {
                    LOG.info(
                        "{}: experience service failure: {}",
                        name, service
                    );
                    // I am not sure what else I could do here.
                    System.exit(1);
                }
            },
            MoreExecutors.directExecutor()
        );

        Runtime.getRuntime().addShutdownHook(new Thread(
            () -> {
                LOG.info(
                    "{}: stop services with {} seconds grace period",
                    name, gracePeriod
                );

                Socket.terminate();

                try {
                    manager.stopAsync().awaitStopped(
                        gracePeriod,
                        TimeUnit.SECONDS
                    );
                } catch (TimeoutException e) {
                    LOG.error(
                        "{}: services do not stop after grace period",
                        name, e
                    );
                }
            },
            name
        ));

        LOG.info("{}: start services", name);
        manager.startAsync();
    }

    public void await() {
        Preconditions.checkState(manager != null);
        manager.awaitStopped();
        LOG.info("{}: exit", name);
    }

    private ImmutableList<Service> makeServices(
        ImmutableList<Handler> handlers
    ) {
        Preconditions.checkState(!handlers.isEmpty());

        ImmutableList.Builder<Service> builder = new ImmutableList.Builder<>();

        Endpoints incoming;
        if (handlers.size() > 1) {
            ImmutableSet<String> address = ImmutableSet.of(routerAddress);
            builder.add(new Router(
                routerName,
                Endpoints.localOnly(serverAddresses),
                Endpoints.localOnly(address)
            ));
            incoming = Endpoints.remoteOnly(address);
        } else {
            incoming = Endpoints.localOnly(serverAddresses);
        }

        int handlerIndex = 1;
        for (Handler handler : handlers) {
            builder.add(new Server(
                String.format(serverNameFormat, handlerIndex),
                incoming,
                handler
            ));
            handlerIndex++;
        }

        return builder.build();
    }

    private static class Endpoints {

        private final ImmutableSet<String> localAddresses;
        private final ImmutableSet<String> remoteAddresses;

        static Endpoints localOnly(ImmutableSet<String> addresses) {
            return new Endpoints(addresses, ImmutableSet.of());
        }

        static Endpoints remoteOnly(ImmutableSet<String> addresses) {
            return new Endpoints(ImmutableSet.of(), addresses);
        }

        Endpoints(
            ImmutableSet<String> localAddresses,
            ImmutableSet<String> remoteAddresses
        ) {
            this.localAddresses = localAddresses;
            this.remoteAddresses = remoteAddresses;
        }

        void applyTo(Socket socket) {
            for (String url : localAddresses) {
                socket.bind(url);
            }
            for (String url : remoteAddresses) {
                socket.connect(url);
            }
        }
    }

    private static class Router extends AbstractExecutionThreadService {

        private final String name;
        private final Endpoints incoming;
        private final Endpoints servers;
        private Socket incomingSocket = null;
        private Socket serversSocket = null;

        Router(String name, Endpoints incoming, Endpoints servers) {
            this.name = name;
            this.incoming = incoming;
            this.servers = servers;
        }

        private void closeSockets() {
            Socket[] sockets = new Socket[]{incomingSocket, serversSocket};
            for (Socket socket : sockets) {
                if (socket != null) {
                    try {
                        socket.close();
                    } catch (nanomsg.Error.EBADF e) {
                        // Socket has probably been closed already.
                    } catch (nanomsg.Error e) {
                        LOG.error("err when closing {}", socket, e);
                    }
                }
            }
            incomingSocket = serversSocket = null;
        }

        @Override
        protected String serviceName() {
            return name;
        }

        @Override
        protected void startUp() throws Exception {
            Preconditions.checkState(
                incomingSocket == null && serversSocket == null);

            try {

                incomingSocket = new Socket(AF_SP_RAW, NN_REP);
                incoming.applyTo(incomingSocket);

                serversSocket = new Socket(AF_SP_RAW, NN_REQ);
                servers.applyTo(serversSocket);

            } catch (Throwable e) {
                closeSockets();
                throw e;
            }
        }

        @Override
        protected void run() throws Exception {
            Preconditions.checkState(
                incomingSocket != null && serversSocket != null);

            if (isRunning()) {
                LOG.info("route requests");
                try {
                    Socket.device(incomingSocket, serversSocket);
                } catch (nanomsg.Error.EBADF e) {
                    LOG.info(
                        "socket has probably been closed: {}, {}",
                        incomingSocket, serversSocket
                    );
                }
            }
        }

        @Override
        protected void shutDown() throws Exception {
            Preconditions.checkState(
                incomingSocket != null && serversSocket != null);
            closeSockets();
        }
    }

    private static class Server extends AbstractExecutionThreadService {

        private final String name;
        private final Endpoints incoming;
        private final Handler handler;
        private Socket socket = null;

        Server(String name, Endpoints incoming, Handler handler) {
            this.name = name;
            this.incoming = Preconditions.checkNotNull(incoming);
            this.handler = Preconditions.checkNotNull(handler);
        }

        private void closeSocket() {
            if (socket != null) {
                try {
                    socket.close();
                } catch (nanomsg.Error.EBADF e) {
                    // Socket has probably been closed already.
                } catch (nanomsg.Error e) {
                    LOG.error("err when closing {}", socket, e);
                }
            }
            socket = null;
        }

        @Override
        protected String serviceName() {
            return name;
        }

        @Override
        protected void startUp() throws Exception {
            Preconditions.checkState(socket == null);
            try {
                socket = new Socket(AF_SP, NN_REP);
                incoming.applyTo(socket);
            } catch (Throwable e) {
                closeSocket();
                throw e;
            }
        }

        @Override
        protected void run() throws Exception {
            Preconditions.checkState(socket != null);

            while (isRunning()) {

                ByteBuffer request;
                try (Message message = socket.recv()) {
                    request = message.getByteBuffer();
                } catch (nanomsg.Error.EBADF e) {
                    LOG.info("socket has probably been closed: {}", socket);
                    break;
                }
                LOG.debug("receive request: size={}", request.remaining());

                ByteBuffer response;
                try {
                    response = handler.handle(request);
                } catch (Exception e) {
                    LOG.error("cannot process request: {}", socket, e);
                    continue;
                }

                LOG.debug("send response: size={}", response.remaining());
                try {
                    socket.send(response);
                } catch (nanomsg.Error.EBADF e) {
                    LOG.info("socket has probably been closed: {}", socket);
                    break;
                }
            }
        }

        @Override
        protected void shutDown() throws Exception {
            Preconditions.checkState(socket != null);
            closeSocket();
        }
    }
}
