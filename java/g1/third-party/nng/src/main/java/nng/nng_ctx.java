package nng;

import com.sun.jna.Pointer;
import com.sun.jna.Structure;

/**
 * Map {@code nng_ctx} type.
 * <p>
 * TODO: It is a little bit unsettling that we map {@code uint32_t} to
 * signed int, but I do not have any better idea for now.
 */
@Structure.FieldOrder({"id"})
public class nng_ctx extends Structure {
    public /* uint32_t */ int id;

    public nng_ctx() {
        super();
    }

    public nng_ctx(Pointer pointer) {
        super(pointer);
        read();
    }

    public static class ByValue extends nng_ctx implements Structure.ByValue {
        public ByValue() {
            super();
        }

        public ByValue(Pointer pointer) {
            super(pointer);
        }

        public ByValue(nng_ctx context) {
            super(context.getPointer());
            id = context.id;
        }
    }
}
