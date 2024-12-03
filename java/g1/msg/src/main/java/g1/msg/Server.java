package g1.msg;

import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.base.Names;
import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import javax.annotation.Nonnull;

// Use `AbstractExecutionThreadService` because `ZMQ.Socket` must not be shared among threads.
class Server extends AbstractExecutionThreadService {
    private static final Names NAMES = new Names("server");

    private final String name;

    private final ZContext context;

    private final ZMQ.Socket frontend;

    private final ZMQ.Socket backend;
    private final String backendUrl;

    private final ZMQ.Socket[] control;

    Server(String url) {
        super();

        this.name = NAMES.next();

        this.context = new ZContext();
        context.setLinger(0); // Do NOT block the program exit!

        this.frontend = context.createSocket(SocketType.ROUTER);
        frontend.bind(url);

        this.backend = context.createSocket(SocketType.DEALER);
        this.backendUrl = String.format("inproc://%s/backend", name);
        backend.bind(backendUrl);

        this.control = new ZMQ.Socket[]{
            context.createSocket(SocketType.PUB),
            context.createSocket(SocketType.SUB),
        };
        String controlUrl = String.format("inproc://%s/control", name);
        control[0].bind(controlUrl);
        control[1].connect(controlUrl);
        control[1].subscribe(new byte[0]);
    }

    @Override
    @Nonnull
    protected String serviceName() {
        return name;
    }

    HandlerContainer createHandlerContainer(Handler handler) {
        ZMQ.Socket socket = context.createSocket(SocketType.REP);
        socket.connect(backendUrl);
        return new HandlerContainer(socket, handler);
    }

    @Override
    protected void run() {
        while (isRunning()) {
            // TODO: Should we check the return value of `ZMQ.proxy`?
            ZMQ.proxy(frontend, backend, null, control[1]);
        }
    }

    @Override
    protected void triggerShutdown() {
        control[0].send(ZMQ.PROXY_TERMINATE);
    }

    @Override
    protected void shutDown() {
        frontend.close();
        backend.close();
        control[0].close();
        control[1].close();

        context.destroy();
    }
}
