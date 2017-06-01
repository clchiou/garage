package garage.search.extractor;

import com.google.common.base.Preconditions;
import dagger.BindsInstance;

import javax.annotation.Nullable;
import javax.inject.Inject;
import javax.inject.Named;
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

import garage.base.MoreFiles;

public class DirectoryExtractor {

    public interface DaggerBuilderMixin<T> {
        @BindsInstance
        T directoryExtractorRoot(@Named("DirectoryExtractor.root") Path root);
    }

    public interface Predicate {
        boolean test(Path file, BasicFileAttributes attrs) throws IOException;
    }

    public interface Consumer {
        void consume(Path file, BasicFileAttributes attrs) throws Exception;
    }

    private final Path root;
    private final Predicate predicate;

    @Inject
    public DirectoryExtractor(
        @Named("DirectoryExtractor.root") Path root,
        @Nullable Predicate predicate
    ) {
        Preconditions.checkArgument(MoreFiles.isReadableDirectory(root));
        this.root = root;
        this.predicate = predicate;
    }

    public void extract(Consumer consumer) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                Path file,
                BasicFileAttributes attrs
            ) throws IOException {
                try {
                    if (predicate == null || predicate.test(file, attrs)) {
                        consumer.consume(file, attrs);
                    }
                } catch (IOException e) {
                    throw e;
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
