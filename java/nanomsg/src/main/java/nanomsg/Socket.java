package nanomsg;

import com.google.common.base.Joiner;
import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;
import com.sun.jna.Memory;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.PointerByReference;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import nanomsg.Nanomsg.size_t;
import nanomsg.Nanomsg.size_t_ptr;

import static nanomsg.Error.check;
import static nanomsg.Nanomsg.NANOMSG;
import static nanomsg.Nanomsg.NN_MSG;
import static nanomsg.Symbol.NN_SOL_SOCKET;

public class Socket implements AutoCloseable {

    public static void device(Socket s1, Socket s2) {
        synchronized (s1) {
            synchronized (s2) {
                Preconditions.checkArgument(s1.socket != -1);
                Preconditions.checkArgument(s2.socket != -1);
                check(NANOMSG.nn_device(s1.socket, s2.socket));
            }
        }
    }

    public static void terminate() {
        NANOMSG.nn_term();
    }

    static {
        Preconditions.checkState(
            NN_SOL_SOCKET.namespace == Namespace.NN_NS_OPTION_LEVEL);
    }

    private static final Joiner JOINER = Joiner.on(',');

    private int socket;
    private final Domain domain;
    private final Protocol protocol;
    private final Map<String, Integer> localEndpoints;
    private final Map<String, Integer> remoteEndpoints;

    public Socket(Domain domain, Protocol protocol) {
        socket = check(NANOMSG.nn_socket(domain.value, protocol.value));

        this.domain = domain;
        this.protocol = protocol;

        localEndpoints = Maps.newLinkedHashMap();
        remoteEndpoints = Maps.newLinkedHashMap();
    }

    @Override
    public String toString() {
        // It may have race condition here, but we probably should not
        // fix it.  Otherwise, we cannot "print" a socket when another
        // thread is locking it (which is annoying).
        return String.format(
            "Socket<%s, %s, socket=%d, local=[%s], remote=[%s]>",
            domain.name(),
            protocol.name(),
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

    public synchronized int getOption(Option option) {
        Preconditions.checkState(socket != -1);

        // Should we support other types?
        Preconditions.checkArgument(
            option.type == Option.Type.NN_TYPE_INT,
            "Expect only integer-typed option: option=%s, type=%s",
            option.name(), option.type.name()
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

    public synchronized void setOption(Option option, Object newValue) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(Option.WRITABLE.contains(option));

        Pointer optval;
        size_t optvallen;

        if (option.type == Option.Type.NN_TYPE_INT) {

            Preconditions.checkArgument(
                Integer.class.isAssignableFrom(newValue.getClass()),
                "Expect integer value: option=%s, value=%s",
                option.name(), newValue
            );

            IntByReference iref = new IntByReference();
            iref.setValue((Integer) newValue);
            optval = iref.getPointer();
            optvallen = new size_t(4);

        } else if (option.type == Option.Type.NN_TYPE_STR) {

            Preconditions.checkArgument(
                String.class.isAssignableFrom(newValue.getClass()),
                "Expect string value: option=%s, value=%s",
                option.name(), newValue
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
                option.name(), option.type.name()
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

    public synchronized void send(byte[] buffer, int offset, int size) {
        Preconditions.checkState(socket != -1);
        Preconditions.checkArgument(offset >= 0 && size >= 0);
        Preconditions.checkArgument(buffer.length >= offset + size);

        if (size == 0) {
            return;
        }

        send(ByteBuffer.wrap(buffer, offset, size));
    }

    public synchronized void send(ByteBuffer buffer) {
        Preconditions.checkState(socket != -1);

        if (buffer.remaining() == 0) {
            return;
        }

        int n = check(NANOMSG.nn_send(
            socket,
            buffer,
            new size_t(buffer.remaining()),
            0
        ));
        Preconditions.checkState(
            n == buffer.remaining(),
            "Expect message to be sent in entirety: %s != %s",
            n, buffer.remaining()
        );
        buffer.position(buffer.position() + n);
    }

    public synchronized Message recv() {
        Preconditions.checkState(socket != -1);

        PointerByReference pref = new PointerByReference();
        int n = check(NANOMSG.nn_recv(socket, pref, NN_MSG, 0));

        return new Message(pref.getValue(), n);
    }
}
