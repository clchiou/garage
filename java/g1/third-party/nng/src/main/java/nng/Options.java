package nng;

import com.sun.jna.ptr.ByReference;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.LongByReference;
import com.sun.jna.ptr.PointerByReference;

import java.nio.charset.StandardCharsets;

import static com.google.common.base.Preconditions.checkState;
import static nng.Error.check;
import static nng.Nng.NNG;

/**
 * Higher-level representation of options.
 */
public enum Options {
    //
    // Generic options.
    //

    NNG_OPT_SOCKNAME("socket-name", Units.STRING, true),
    NNG_OPT_RAW("raw", Units.BOOL, false),
    NNG_OPT_PROTO("protocol", Units.INT, false),
    NNG_OPT_PROTONAME("protocol-name", Units.STRING, false),
    NNG_OPT_PEER("peer", Units.INT, false),
    NNG_OPT_PEERNAME("peer-name", Units.STRING, false),
    NNG_OPT_RECVBUF("recv-buffer", Units.INT, true),
    NNG_OPT_SENDBUF("send-buffer", Units.INT, true),
    NNG_OPT_RECVFD("recv-fd", Units.INT, false),
    NNG_OPT_SENDFD("send-fd", Units.INT, false),
    NNG_OPT_RECVTIMEO("recv-timeout", Units.MILLISECOND, true),
    NNG_OPT_SENDTIMEO("send-timeout", Units.MILLISECOND, true),
    // TODO: Add mapping for nng_sockaddr.
    // NNG_OPT_LOCADDR("local-address", Units.SOCKET_ADDRESS, false),
    // NNG_OPT_REMADDR("remote-address", Units.SOCKET_ADDRESS, false),
    NNG_OPT_URL("url", Units.STRING, false),
    NNG_OPT_MAXTTL("ttl-max", Units.INT, true),
    NNG_OPT_RECVMAXSZ("recv-size-max", Units.SIZE, true),
    NNG_OPT_RECONNMINT("reconnect-time-min", Units.MILLISECOND, true),
    NNG_OPT_RECONNMAXT("reconnect-time-max", Units.MILLISECOND, true),

    //
    // Transport options.
    //

    // TCP options.
    NNG_OPT_TCP_NODELAY("tcp-nodelay", Units.BOOL, true),
    NNG_OPT_TCP_KEEPALIVE("tcp-keepalive", Units.BOOL, true),
    NNG_OPT_TCP_BOUND_PORT("tcp-bound-port", Units.INT, false),

    //
    // Protocol options.
    //

    // Protocol "pubsub0" options.
    NNG_OPT_SUB_SUBSCRIBE("sub:subscribe", Units.STRING, true),
    NNG_OPT_SUB_UNSUBSCRIBE("sub:unsubscribe", Units.STRING, true),

    // Protocol "reqrep0" options.
    NNG_OPT_REQ_RESENDTIME("req:resend-time", Units.MILLISECOND, true),

    // Protocol "survey0" options.
    NNG_OPT_SURVEYOR_SURVEYTIME(
        "surveyor:survey-time", Units.MILLISECOND, true
    );

    private final String name;
    private final Units unit;
    private final boolean readwrite;

    Options(String name, Units unit, boolean readwrite) {
        this.name = name;
        this.unit = unit;
        this.readwrite = readwrite;
    }

    /* package private */ Object get(nng_socket.ByValue socket) {
        switch (unit) {
            case BOOL:
                return get(
                    socket, NNG::nng_socket_get_bool, new BoolByReference()
                ).getValue();
            case INT:
                return get(
                    socket, NNG::nng_socket_get_int, new IntByReference()
                ).getValue();
            case MILLISECOND:
                return get(
                    socket, NNG::nng_socket_get_ms, new IntByReference()
                ).getValue();
            case SIZE:
                return get(
                    socket, NNG::nng_socket_get_size, new LongByReference()
                ).getValue();
            case STRING:
                return get(
                    socket,
                    NNG::nng_socket_get_string,
                    new PointerByReference()
                ).getValue().getString(0, StandardCharsets.UTF_8.name());
            default:
                throw new AssertionError("unhandled unit: " + unit);
        }
    }

    private <RefType extends ByReference> RefType get(
        nng_socket.ByValue socket, Getter<RefType> getter, RefType ref
    ) {
        check(getter.get(socket, name, ref));
        return ref;
    }

    /* package private */ void set(nng_socket.ByValue socket, Object value) {
        checkState(readwrite);
        switch (unit) {
            case BOOL:
                check(NNG.nng_socket_set_bool(socket, name, (Boolean) value));
                break;
            case INT:
                check(NNG.nng_socket_set_int(socket, name, (Integer) value));
                break;
            case MILLISECOND:
                check(NNG.nng_socket_set_ms(socket, name, (Integer) value));
                break;
            case SIZE:
                check(NNG.nng_socket_set_size(socket, name, (Long) value));
                break;
            case STRING:
                check(NNG.nng_socket_set_string(socket, name, (String) value));
                break;
            default:
                throw new AssertionError("unhandled unit: " + unit);
        }
    }

    private interface Getter<RefType extends ByReference> {
        int get(nng_socket.ByValue socket, String name, RefType ref);
    }
}
