package nng;

import com.sun.jna.Pointer;
import com.sun.jna.Structure;

/**
 * Map {@code nng_socket} type.
 * <p>
 * TODO: It is a little bit unsettling that we map {@code uint32_t} to
 * signed int, but I do not have any better idea for now.
 */
@Structure.FieldOrder({"id"})
public class nng_socket extends Structure {
    public /* uint32_t */ int id;

    public nng_socket() {
        super();
    }

    public nng_socket(Pointer pointer) {
        super(pointer);
        read();
    }

    public static class ByValue
        extends nng_socket implements Structure.ByValue {

        public ByValue() {
            super();
        }

        public ByValue(Pointer pointer) {
            super(pointer);
        }

        public ByValue(nng_socket socket) {
            super(socket.getPointer());
            id = socket.id;
        }
    }
}
