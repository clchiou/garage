package nanomsg;

import com.google.common.annotations.VisibleForTesting;
import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.sun.jna.Library;
import com.sun.jna.IntegerType;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.Structure;
import com.sun.jna.ptr.ByReference;
import com.sun.jna.ptr.PointerByReference;

import java.nio.ByteBuffer;
import java.util.List;

/**
 * Wrap nanomsg library with JNA.
 *
 * This is low-level interface, which should not be used externally.
 *
 * If later performance becomes an issue, we might rewrite this project
 * with JNI (but I doubt it).
 */
class Nanomsg {

    private Nanomsg() {
        throw new AssertionError();
    }

    /**
     * Map size_t to Java long type.
     */
    public static class size_t extends IntegerType {

        public size_t() {
            this(0L);
        }

        public size_t(long value) {
            super(Native.SIZE_T_SIZE, value);
        }
    }

    public static class size_t_ptr extends ByReference {

        public size_t_ptr() {
            this(0L);
        }

        public size_t_ptr(long value) {
            super(Native.SIZE_T_SIZE);
            setValue(value);
        }

        public long getValue() {
            return getPointer().getLong(0L);
        }

        public void setValue(long value) {
            getPointer().setLong(0L, value);
        }
    }

    public static class nn_symbol_properties extends Structure {

        public int value;

        public String name;

        public int ns;

        public int type;

        public int unit;

        private static final List<String> FIELD_ORDER = ImmutableList.of(
            "value", "name", "ns", "type", "unit"
        );

        @Override
        protected List<String> getFieldOrder() {
            return FIELD_ORDER;
        }
    }

    /**
     * Nanomsg function declarations.
     *
     * You must keep these signatures in sync with C headers.
     */
    interface NanomsgLibrary extends Library {

        int nn_errno();

        String nn_strerror(int errnum);

        int nn_symbol_info(int i, nn_symbol_properties buf, int buflen);

        void nn_term();

        int nn_freemsg(Pointer msg);

        int nn_socket(int domain, int protocol);

        int nn_close(int s);

        int nn_getsockopt(
            int s, int level, int option,
            Pointer optval, size_t_ptr optvallen
        );

        int nn_setsockopt(
            int s, int level, int option,
            Pointer optval, size_t optvallen
        );

        int nn_bind(int s, String addr);

        int nn_connect(int s, String addr);

        int nn_shutdown(int s, int how);

        int nn_send(int s, ByteBuffer buf, size_t len, int flags);

        int nn_recv(int s, PointerByReference buf, size_t len, int flags);

        int nn_device(int s1, int s2);
    }

    static final size_t NN_MSG = new size_t(-1);

    static final NanomsgLibrary NANOMSG = (NanomsgLibrary) Native.loadLibrary(
        "nanomsg",
        NanomsgLibrary.class
    );

    /*
     * Load symbol properties from the library.
     */

    @VisibleForTesting
    static final ImmutableMap<String, nn_symbol_properties> SYMBOLS;
    static {
        ImmutableMap.Builder<String, nn_symbol_properties> builder =
            new ImmutableMap.Builder<>();
        for (int i = 0; ; i++) {
            nn_symbol_properties symbol = new nn_symbol_properties();
            if (NANOMSG.nn_symbol_info(i, symbol, symbol.size()) == 0) {
                break;
            }
            builder.put(symbol.name, symbol);
        }
        SYMBOLS = builder.build();
    }

    static nn_symbol_properties symbol(String symbol) {
        return Preconditions.checkNotNull(SYMBOLS.get(symbol));
    }
}
