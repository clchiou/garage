package g1.base;

/**
 * Generate {@code Service} instance names.
 */
public class Names {
    private final String format;
    private int n;

    public Names(String prefix) {
        this.format = prefix + "-%02d";
        this.n = 0;
    }

    public synchronized String next() {
        return String.format(format, n++);
    }
}
