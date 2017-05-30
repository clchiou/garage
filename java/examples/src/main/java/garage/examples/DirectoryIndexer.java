package garage.examples;

import com.google.common.base.Preconditions;
import dagger.Component;
import dagger.Module;
import dagger.Provides;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.LongPoint;
import org.apache.lucene.document.StringField;
import org.apache.lucene.document.TextField;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Singleton;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.MoreFiles;
import garage.search.indexer.BatchIndexer;

@Component(modules = DirectoryIndexer.DirectoryIndexerModule.class)
@Singleton
public interface DirectoryIndexer {

    @Module
    class DirectoryIndexerModule {

        private final Configuration config;

        public DirectoryIndexerModule(Configuration config) {
            this.config = config;
        }

        @Provides
        @Singleton
        public Configuration provideConfig() {
            return config;
        }

        @Provides
        @Singleton
        public Analyzer provideAnalyzer() {
            return new StandardAnalyzer();
        }
    }

    BatchIndexer openIndexer();

    static void main(Configuration.Args args) throws Exception {

        final Logger LOG = LoggerFactory.getLogger(DirectoryIndexer.class);

        Configuration config = Configuration
            .parse(args)
            .getOrThrow("directory_indexer", Configuration.class);

        Path source = Paths.get(config.getOrThrow("source", String.class));
        Preconditions.checkArgument(MoreFiles.isReadableDirectory(source));

        DirectoryIndexer directoryIndexer = DaggerDirectoryIndexer.builder()
            .directoryIndexerModule(new DirectoryIndexerModule(config))
            .build();

        try (BatchIndexer indexer = directoryIndexer.openIndexer()) {
            Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                    Path file,
                    BasicFileAttributes attrs
                ) throws IOException {
                    try (Reader reader = Files.newBufferedReader(file)) {
                        Document doc = new Document();
                        doc.add(new StringField(
                            "path", file.toString(),
                            Field.Store.YES
                        ));
                        doc.add(new LongPoint(
                            "last_modified",
                            attrs.lastModifiedTime().toMillis()
                        ));
                        doc.add(new TextField("contents", reader));
                        indexer.index(doc);
                    } catch (IOException e) {
                        // We just carry on at the moment.
                        LOG.warn("err while indexing {}: {}", file, e);
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    static void main(String[] args) {
        Application.run(
            args, new Configuration.Args(),
            DirectoryIndexer::main
        );
    }
}
