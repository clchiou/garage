package nanomsg;

import com.google.common.collect.ImmutableMap;

import nanomsg.Symbol.Namespace;

import java.util.Optional;

import static nanomsg.Nanomsg.NANOMSG;

public class Error extends RuntimeException {

    /**
     * Check function return value.
     *
     * The convention of nanomsg is that -1 means error.
     */
    static int check(int ret) {
        if (ret < 0) {
            throw new Error(NANOMSG.nn_errno());
        }
        return ret;
    }

    /**
     * Reverse look-up table of Error constants.
     */
    private static final ImmutableMap<Integer, Symbol> ERROR_SYMBOLS;
    static {
        ImmutableMap.Builder<Integer, Symbol> builder =
            new ImmutableMap.Builder<>();
        for (Symbol symbol : Symbol.values()) {
            if (symbol.namespace == Namespace.NN_NS_ERROR) {
                builder.put(symbol.value, symbol);
            }
        }
        ERROR_SYMBOLS = builder.build();
    }

    public final int errno;

    public Error(int errno) {
        this.errno = errno;
    }

    public Optional<Symbol> asSymbol() {
        return Optional.ofNullable(ERROR_SYMBOLS.get(errno));
    }

    @Override
    public String toString() {
        return String.format(
            "Error<%s(%d): %s>",
            asSymbol().map((e) -> e.name).orElse("UNKNOWN"),
            errno, NANOMSG.nn_strerror(errno)
        );
    }

    @Override
    public boolean equals(Object obj) {
        if (obj == null) {
            return false;
        }
        if (!Error.class.isAssignableFrom(obj.getClass())) {
            return false;
        }
        Error other = (Error) obj;
        return errno == other.errno;
    }

    @Override
    public int hashCode() {
        return errno;
    }
}
