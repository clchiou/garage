package nng;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.LongByReference;
import com.sun.jna.ptr.PointerByReference;

/**
 * Mapping the libnng library.
 * <p>
 * This is not a complete mapping of libnng, but rather just the needed
 * interface for implementing the higher-level interface.
 * <p>
 * TODO: It is a little bit unsettling that we map {@code size_t} and
 * {@code uint64_t} to signed int/long, but I do not have any better
 * idea for now.
 * <p>
 * In theory JNA is slower than JNI, but I guess the performance
 * difference is negligible in our use cases.
 */
public interface Nng extends Library {
    Nng NNG = load();

    // Use a function because interface does not allow a static block.
    static Nng load() {
        // size_t has yet to be exposed in JNA public interface; so we
        // map it to long instead.
        // https://github.com/java-native-access/jna/issues/1113
        if (Native.SIZE_T_SIZE != 8) {
            throw new AssertionError("expect sizeof(size_t) == 8");
        }
        return Native.load("nng", Nng.class);
    }

    //
    // Common functions.
    //

    void nng_closeall();

    String nng_strerror(int errno);

    //
    // Socket functions.
    //

    int nng_close(nng_socket.ByValue socket);

    int nng_socket_get(
        nng_socket.ByValue socket,
        String option,
        byte[] value,
        /* size_t* */ LongByReference size
    );

    int nng_socket_get_bool(
        nng_socket.ByValue socket, String option, BoolByReference value
    );

    int nng_socket_get_int(
        nng_socket.ByValue socket, String option, IntByReference value
    );

    int nng_socket_get_ms(
        nng_socket.ByValue socket,
        String option,
        /* nng_duration* */ IntByReference value
    );

    int nng_socket_get_uint64(
        nng_socket.ByValue socket,
        String option,
        /* uint64_t* */ LongByReference value
    );

    int nng_socket_get_size(
        nng_socket.ByValue socket,
        String option,
        /* size_t* */ LongByReference value
    );

    int nng_socket_get_ptr(
        nng_socket.ByValue socket, String option, PointerByReference value
    );

    int nng_socket_get_string(
        nng_socket.ByValue socket,
        String option,
        /* char** */ PointerByReference value
    );
    // TODO: Add mapping for nng_sockaddr and NngSockaddrByReference.
    // int nng_socket_get_addr(
    //     nng_socket.ByValue socket,
    //     String option,
    //     NngSockaddrByReference value
    // );

    int nng_socket_set(
        nng_socket.ByValue socket,
        String option,
        byte[] value,
        /* size_t */ long size
    );

    int nng_socket_set_bool(
        nng_socket.ByValue socket, String option, boolean value
    );

    int nng_socket_set_int(
        nng_socket.ByValue socket, String option, int value
    );

    int nng_socket_set_ms(
        nng_socket.ByValue socket, String option, /* nng_duration */ int value
    );

    int nng_socket_set_uint64(
        nng_socket.ByValue socket, String option, /* uint64_t */ long value
    );

    int nng_socket_set_size(
        nng_socket.ByValue socket, String option, /* size_t */ long value
    );

    int nng_socket_set_ptr(
        nng_socket.ByValue socket, String option, Pointer value
    );

    int nng_socket_set_string(
        nng_socket.ByValue socket, String option, String value
    );

    int nng_sendmsg(
        nng_socket.ByValue socket,
        /* nng_msg* */ Pointer message,
        int flags
    );

    int nng_recvmsg(
        nng_socket.ByValue socket,
        /* nng_msg** */ PointerByReference message,
        int flags
    );

    //
    // Context functions.
    //

    int nng_ctx_open(nng_ctx context, nng_socket.ByValue socket);

    int nng_ctx_close(nng_ctx.ByValue context);

    void nng_ctx_send(nng_ctx.ByValue context, /* nng_aio* */ Pointer aio);

    void nng_ctx_recv(nng_ctx.ByValue context, /* nng_aio* */ Pointer aio);

    //
    // Protocols.
    //

    int nng_bus0_open(nng_socket socket);

    int nng_bus0_open_raw(nng_socket socket);

    int nng_pair0_open(nng_socket socket);

    int nng_pair0_open_raw(nng_socket socket);

    int nng_pair1_open(nng_socket socket);

    int nng_pair1_open_raw(nng_socket socket);

    int nng_pull0_open(nng_socket socket);

    int nng_pull0_open_raw(nng_socket socket);

    int nng_push0_open(nng_socket socket);

    int nng_push0_open_raw(nng_socket socket);

    int nng_pub0_open(nng_socket socket);

    int nng_pub0_open_raw(nng_socket socket);

    int nng_sub0_open(nng_socket socket);

    int nng_sub0_open_raw(nng_socket socket);

    int nng_rep0_open(nng_socket socket);

    int nng_rep0_open_raw(nng_socket socket);

    int nng_req0_open(nng_socket socket);

    int nng_req0_open_raw(nng_socket socket);

    int nng_respondent0_open(nng_socket socket);

    int nng_respondent0_open_raw(nng_socket socket);

    int nng_surveyor0_open(nng_socket socket);

    int nng_surveyor0_open_raw(nng_socket socket);

    //
    // Dialer functions.
    //

    // TODO: Add mapping for nng_dialer.
    int nng_dial(
        nng_socket.ByValue socket,
        String url,
        /* nng_dialer* */ Pointer dialer,
        int flags
    );

    //
    // Listener functions.
    //

    // TODO: Add mapping for nng_listener.
    int nng_listen(
        nng_socket.ByValue socket,
        String url,
        /* nng_listener* */ Pointer listener,
        int flags
    );

    //
    // Message functions.
    //

    int nng_msg_alloc(
        /* nng_msg** */ PointerByReference message, /* size_t */ long size
    );

    void nng_msg_free(/* nng_msg* */ Pointer message);

    Pointer nng_msg_body(/* nng_msg* */ Pointer message);

    /* size_t */ long nng_msg_len(/* nng_msg* */ Pointer message);

    int nng_msg_append(
        /* nng_msg* */ Pointer message, byte[] value, /* size_t */ long size
    );

    //
    // AIO functions.
    //

    int nng_aio_alloc(
        /* nng_aio** */ PointerByReference aio,
        /* void (*)(void*) */ Pointer callback,
        /* void* */ Pointer argument
    );

    void nng_aio_free(/* nng_aio* */ Pointer aio);

    void nng_aio_set_timeout(
        /* nng_aio* */ Pointer aio, /* nng_duration */ int timeout
    );

    /* nng_msg* */ Pointer nng_aio_get_msg(/* nng_aio* */ Pointer aio);

    void nng_aio_set_msg(
        /* nng_aio* */ Pointer aio, /* nng_msg* */ Pointer message
    );

    void nng_aio_wait(/* nng_aio* */ Pointer aio);

    int nng_aio_result(/* nng_aio* */ Pointer aio);
}
