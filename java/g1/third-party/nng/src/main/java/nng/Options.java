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

    NNG_OPT_SOCKNAME("socket-name", Units.STRING, true, true),
    NNG_OPT_RAW("raw", Units.BOOL, true, false),
    NNG_OPT_PROTO("protocol", Units.INT, true, false),
    NNG_OPT_PROTONAME("protocol-name", Units.STRING, true, false),
    NNG_OPT_PEER("peer", Units.INT, true, false),
    NNG_OPT_PEERNAME("peer-name", Units.STRING, true, false),
    NNG_OPT_RECVBUF("recv-buffer", Units.INT, true, true),
    NNG_OPT_SENDBUF("send-buffer", Units.INT, true, true),
    NNG_OPT_RECVFD("recv-fd", Units.INT, true, false),
    NNG_OPT_SENDFD("send-fd", Units.INT, true, false),
    NNG_OPT_RECVTIMEO("recv-timeout", Units.MILLISECOND, true, true),
    NNG_OPT_SENDTIMEO("send-timeout", Units.MILLISECOND, true, true),
    // TODO: Add mapping for nng_sockaddr.
    // NNG_OPT_LOCADDR("local-address", Units.SOCKET_ADDRESS, true, false),
    // NNG_OPT_REMADDR("remote-address", Units.SOCKET_ADDRESS, true, false),
    NNG_OPT_URL("url", Units.STRING, true, false),
    NNG_OPT_MAXTTL("ttl-max", Units.INT, true, true),
    NNG_OPT_RECVMAXSZ("recv-size-max", Units.SIZE, true, true),
    NNG_OPT_RECONNMINT("reconnect-time-min", Units.MILLISECOND, true, true),
    NNG_OPT_RECONNMAXT("reconnect-time-max", Units.MILLISECOND, true, true),

    //
    // Transport options.
    //

    // TCP options.
    NNG_OPT_TCP_NODELAY("tcp-nodelay", Units.BOOL, true, true),
    NNG_OPT_TCP_KEEPALIVE("tcp-keepalive", Units.BOOL, true, true),
    NNG_OPT_TCP_BOUND_PORT("tcp-bound-port", Units.INT, true, false),

    //
    // Protocol options.
    //

    // Protocol "pubsub0" options.
    NNG_OPT_SUB_SUBSCRIBE("sub:subscribe", Units.BYTES, false, true),
    NNG_OPT_SUB_UNSUBSCRIBE("sub:unsubscribe", Units.BYTES, false, true),

    // Protocol "reqrep0" options.
    NNG_OPT_REQ_RESENDTIME("req:resend-time", Units.MILLISECOND, true, true),

    // Protocol "survey0" options.
    NNG_OPT_SURVEYOR_SURVEYTIME(
        "surveyor:survey-time", Units.MILLISECOND, true, true
    );

    private final String name;
    private final Units unit;
    private final boolean readable;
    private final boolean writable;

    Options(String name, Units unit, boolean readable, boolean writable) {
        this.name = name;
        this.unit = unit;
        this.readable = readable;
        this.writable = writable;
    }

    /* package private */ Object get(nng_socket.ByValue socket) {
        checkState(readable);
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

    /* package private */ Object get(nng_ctx.ByValue socket) {
        checkState(readable);
        switch (unit) {
            case BOOL:
                return get(
                    socket, NNG::nng_ctx_get_bool, new BoolByReference()
                ).getValue();
            case INT:
                return get(
                    socket, NNG::nng_ctx_get_int, new IntByReference()
                ).getValue();
            case MILLISECOND:
                return get(
                    socket, NNG::nng_ctx_get_ms, new IntByReference()
                ).getValue();
            case SIZE:
                return get(
                    socket, NNG::nng_ctx_get_size, new LongByReference()
                ).getValue();
            case STRING:
                return get(
                    socket,
                    NNG::nng_ctx_get_string,
                    new PointerByReference()
                ).getValue().getString(0, StandardCharsets.UTF_8.name());
            default:
                throw new AssertionError("unhandled unit: " + unit);
        }
    }

    private <RefType extends ByReference> RefType get(
        nng_socket.ByValue socket, SocketGetter<RefType> getter, RefType ref
    ) {
        check(getter.get(socket, name, ref));
        return ref;
    }

    private <RefType extends ByReference> RefType get(
        nng_ctx.ByValue context, ContextGetter<RefType> getter, RefType ref
    ) {
        check(getter.get(context, name, ref));
        return ref;
    }

    /* package private */ void set(nng_socket.ByValue socket, Object value) {
        checkState(writable);
        switch (unit) {
            case BYTES: {
                byte[] bs = (byte[]) value;
                check(NNG.nng_socket_set(socket, name, bs, bs.length));
                break;
            }
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

    /* package private */ void set(nng_ctx.ByValue socket, Object value) {
        checkState(writable);
        switch (unit) {
            case BYTES: {
                byte[] bs = (byte[]) value;
                check(NNG.nng_ctx_set(socket, name, bs, bs.length));
                break;
            }
            case BOOL:
                check(NNG.nng_ctx_set_bool(socket, name, (Boolean) value));
                break;
            case INT:
                check(NNG.nng_ctx_set_int(socket, name, (Integer) value));
                break;
            case MILLISECOND:
                check(NNG.nng_ctx_set_ms(socket, name, (Integer) value));
                break;
            case SIZE:
                check(NNG.nng_ctx_set_size(socket, name, (Long) value));
                break;
            case STRING:
                check(NNG.nng_ctx_set_string(socket, name, (String) value));
                break;
            default:
                throw new AssertionError("unhandled unit: " + unit);
        }
    }

    private interface SocketGetter<RefType extends ByReference> {
        int get(nng_socket.ByValue socket, String name, RefType ref);
    }

    private interface ContextGetter<RefType extends ByReference> {
        int get(nng_ctx.ByValue context, String name, RefType ref);
    }
}
