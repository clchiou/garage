package nanomsg;

import com.google.common.base.Joiner;
import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;
import com.sun.jna.Memory;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.IntByReference;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import nanomsg.Nanomsg.size_t;
import nanomsg.Nanomsg.size_t_ptr;

import static nanomsg.Error.check;
import static nanomsg.Nanomsg.NANOMSG;
import static nanomsg.Symbol.NN_SOL_SOCKET;

public class Socket implements AutoCloseable {

    public static void device(Socket s1, Socket s2) {
        synchronized (s1) {
            synchronized (s2) {
                check(NANOMSG.nn_device(s1.socket, s2.socket));
            }
        }
    }

    public static void terminate() {
        NANOMSG.nn_term();
    }

    static {
        Preconditions.checkState(
            NN_SOL_SOCKET.namespace == Symbol.Namespace.NN_NS_OPTION_LEVEL);
    }

    private static final Joiner JOINER = Joiner.on(',');

    private int socket;
    private final Map<String, Integer> localEndpoints;
    private final Map<String, Integer> remoteEndpoints;

    public Socket(Symbol domain, Symbol protocol) {
        Preconditions.checkArgument(
            domain.namespace == Symbol.Namespace.NN_NS_DOMAIN);
        Preconditions.checkArgument(
            protocol.namespace == Symbol.Namespace.NN_NS_PROTOCOL);

        socket = -1;
        socket = check(NANOMSG.nn_socket(domain.value, protocol.value));

        localEndpoints = Maps.newLinkedHashMap();
        remoteEndpoints = Maps.newLinkedHashMap();
    }

    @Override
    public String toString() {
        // It may have race condition here, but we probably should not
        // fix it.  Otherwise, we cannot "print" a socket when another
        // thread is locking it (which is annoying).
        return String.format(
            "Socket<socket=%d, local_addrs=[%s], remote_addrs=[%s]>",
            socket,
            JOINER.join(localEndpoints.keySet()),
            JOINER.join(remoteEndpoints.keySet())
        );
    }

    @Override
    public synchronized void close() {
        if (socket == -1) {
            return;
        }
        check(NANOMSG.nn_close(socket));
        socket = -1;
        localEndpoints.clear();
        remoteEndpoints.clear();
    }

    @Override
    protected void finalize() throws Throwable {
        close();
    }

    public synchronized int getOption(Symbol option) {
        Preconditions.checkState(socket != -1);

        Preconditions.checkArgument(
            option.namespace == Symbol.Namespace.NN_NS_SOCKET_OPTION ||
            option.namespace == Symbol.Namespace.NN_NS_TRANSPORT_OPTION
        );

        // Should we support other types?
        Preconditions.checkArgument(
            option.type == Symbol.Type.NN_TYPE_INT,
            "Expect only integer-typed option: option=%s, type=%s",
            option.name, option.type
        );

        IntByReference iref = new IntByReference();
        check(NANOMSG.nn_getsockopt(
            socket,
            NN_SOL_SOCKET.value,
            option.value,
            iref.getPointer(),
            new size_t_ptr(4)
        ));

        return iref.getValue();
    }

    public synchronized void setOption(Symbol option, Object newValue) {
        Preconditions.checkState(socket != -1);

        Preconditions.checkArgument(
            option.namespace == Symbol.Namespace.NN_NS_SOCKET_OPTION ||
            option.namespace == Symbol.Namespace.NN_NS_TRANSPORT_OPTION
        );

        Pointer optval;
        size_t optvallen;

        if (option.type == Symbol.Type.NN_TYPE_INT) {

            Preconditions.checkArgument(
                Integer.class.isAssignableFrom(newValue.getClass()),
                "Expect integer value: option=%s, value=%s",
                option.name, newValue
            );

            IntByReference iref = new IntByReference();
            iref.setValue((Integer) newValue);
            optval = iref.getPointer();
            optvallen = new size_t(4);

        } else if (option.type == Symbol.Type.NN_TYPE_STR) {

            Preconditions.checkArgument(
                String.class.isAssignableFrom(newValue.getClass()),
                "Expect string value: option=%s, value=%s",
                option.name, newValue
            );

            String str = (String) newValue;
            byte[] bytes = str.getBytes(StandardCharsets.US_ASCII);
            Memory buffer = new Memory(bytes.length);
            buffer.write(0, bytes, 0, bytes.length);
            optval = buffer;
            optvallen = new size_t(bytes.length);

        } else {
            throw new AssertionError(String.format(
                "Unsupported type of option: option=%s, type=%s",
                option.name, option.type
            ));
        }

        check(NANOMSG.nn_setsockopt(
            socket,
            NN_SOL_SOCKET.value,
            option.value,
            optval,
            optvallen
        ));
    }

    public synchronized void bind(String address) {
        Preconditions.checkState(socket != -1);

        int endpoint = check(NANOMSG.nn_bind(socket, address));
        localEndpoints.put(address, endpoint);
    }

    public synchronized void connect(String address) {
        Preconditions.checkState(socket != -1);

        int endpoint = check(NANOMSG.nn_connect(socket, address));
        remoteEndpoints.put(address, endpoint);
    }

    public synchronized void shutdown(String address) {
        Preconditions.checkState(socket != -1);

        Map<String, Integer> endpoints;
        if (localEndpoints.containsKey(address)) {
            endpoints = localEndpoints;
        } else if (remoteEndpoints.containsKey(address)) {
            endpoints = remoteEndpoints;
        } else {
            // Should we err out instead?
            return;
        }

        check(NANOMSG.nn_shutdown(
            socket,
            Preconditions.checkNotNull(endpoints.get(address))
        ));

        // Only remove it on success.
        endpoints.remove(address);
    }

    // At the moment we don't take the flags argument in send and recv,
    // but should we?

    public int send(byte[] buffer) {
        return send(buffer, buffer.length);
    }

    public synchronized int send(byte[] buffer, int size) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(buffer.length >= size);

        if (size == 0) {
            return 0;
        }

        return check(NANOMSG.nn_send(socket, buffer, new size_t(size), 0));
    }

    public void send(ByteBuffer buffer) {
        send(buffer, buffer.remaining());
    }

    public synchronized void send(ByteBuffer buffer, int size) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(buffer.remaining() >= size);

        if (size == 0) {
            return;
        }

        int n = check(NANOMSG.nn_send(socket, buffer, new size_t(size), 0));
        buffer.position(buffer.position() + n);
    }

    public int recv(byte[] buffer) {
        return recv(buffer, buffer.length);
    }

    public synchronized int recv(byte[] buffer, int size) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(buffer.length >= size);

        if (size == 0) {
            return 0;
        }

        return check(NANOMSG.nn_recv(socket, buffer, new size_t(size), 0));
    }

    public void recv(ByteBuffer buffer) {
        recv(buffer, buffer.remaining());
    }

    public synchronized void recv(ByteBuffer buffer, int size) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(buffer.remaining() >= size);

        if (size == 0) {
            return;
        }

        int n = check(NANOMSG.nn_recv(socket, buffer, new size_t(size), 0));
        buffer.position(buffer.position() + n);
    }
}
