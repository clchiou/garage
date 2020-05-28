package g1.messaging;

/**
 * Generate service instance names.
 */
public class NameGenerator {
    private final String nameTemplate;
    private int numInstances;

    public NameGenerator(String prefix) {
        this.nameTemplate = prefix + "-%02d";
        this.numInstances = 0;
    }

    public synchronized String next() {
        return String.format(nameTemplate, numInstances++);
    }
}
