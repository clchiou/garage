package garage.base;

import java.nio.file.Files;
import java.nio.file.Path;

public class MoreFiles {

    public static boolean isReadableDirectory(Path path) {
        return Files.isDirectory(path) && Files.isReadable(path);
    }

    public static boolean isReadableFile(Path path) {
        return !Files.isDirectory(path) && Files.isReadable(path);
    }

    public static boolean isWritableDirectory(Path path) {
        return Files.isDirectory(path) && Files.isWritable(path);
    }

    private MoreFiles() {
        throw new AssertionError();
    }
}
