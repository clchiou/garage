package g1.etcd;

import io.etcd.jetcd.ByteSequence;

import java.nio.charset.StandardCharsets;

class ByteSequences {

    private ByteSequences() {
        throw new AssertionError();
    }

    static ByteSequence from(String string) {
        return ByteSequence.from(string, StandardCharsets.UTF_8);
    }

    static String to(ByteSequence bs) {
        return bs.toString(StandardCharsets.UTF_8);
    }
}
