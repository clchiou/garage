package nng;

import static nng.Nng.NNG;

/**
 * Map to libnng errors.
 * <p>
 * This extends RuntimeException so that it is not a checked exception.
 */
public class Error extends RuntimeException {
    // Constants copied from nng.h.
    public static final int NNG_EINTR = 1;
    public static final int NNG_ENOMEM = 2;
    public static final int NNG_EINVAL = 3;
    public static final int NNG_EBUSY = 4;
    public static final int NNG_ETIMEDOUT = 5;
    public static final int NNG_ECONNREFUSED = 6;
    public static final int NNG_ECLOSED = 7;
    public static final int NNG_EAGAIN = 8;
    public static final int NNG_ENOTSUP = 9;
    public static final int NNG_EADDRINUSE = 10;
    public static final int NNG_ESTATE = 11;
    public static final int NNG_ENOENT = 12;
    public static final int NNG_EPROTO = 13;
    public static final int NNG_EUNREACHABLE = 14;
    public static final int NNG_EADDRINVAL = 15;
    public static final int NNG_EPERM = 16;
    public static final int NNG_EMSGSIZE = 17;
    public static final int NNG_ECONNABORTED = 18;
    public static final int NNG_ECONNRESET = 19;
    public static final int NNG_ECANCELED = 20;
    public static final int NNG_ENOFILES = 21;
    public static final int NNG_ENOSPC = 22;
    public static final int NNG_EEXIST = 23;
    public static final int NNG_EREADONLY = 24;
    public static final int NNG_EWRITEONLY = 25;
    public static final int NNG_ECRYPTO = 26;
    public static final int NNG_EPEERAUTH = 27;
    public static final int NNG_ENOARG = 28;
    public static final int NNG_EAMBIGUOUS = 29;
    public static final int NNG_EBADTYPE = 30;
    public static final int NNG_ECONNSHUT = 31;
    public static final int NNG_EINTERNAL = 1000;
    public static final int NNG_ESYSERR = 0x10000000;
    public static final int NNG_ETRANERR = 0x20000000;

    private final int errno;

    public Error(int errno, String message) {
        super(message);
        this.errno = errno;
    }

    /* package private */
    static void check(int errno) {
        if (errno != 0) {
            throw new Error(errno, NNG.nng_strerror(errno));
        }
    }

    public int getErrno() {
        return errno;
    }
}
