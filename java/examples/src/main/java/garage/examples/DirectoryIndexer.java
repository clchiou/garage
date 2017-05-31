package garage.examples;

import com.google.common.base.Preconditions;
import dagger.BindsInstance;
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

import javax.inject.Named;
import javax.inject.Singleton;

import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.Configuration.Node;
import garage.base.MoreFiles;
import garage.search.extractor.DirectoryExtractor;
import garage.search.indexer.BatchIndexer;

@Component(modules = DirectoryIndexer.DirectoryIndexerModule.class)
@Singleton
public interface DirectoryIndexer {

    @Module
    class DirectoryIndexerModule {

        @Provides
        @Named("DirectoryExtractor.root")
        public static Path provideRoot(
            @Node(DirectoryIndexer.class) Configuration config
        ) {
            Path root = Paths.get(config.getOrThrow("root", String.class));
            Preconditions.checkArgument(MoreFiles.isReadableDirectory(root));
            return root;
        }

        @Provides
        public static DirectoryExtractor.Predicate providePredicate() {
            return null;
        }

        @Provides
        @Singleton
        @Node(BatchIndexer.class)
        public static Configuration provideConfig(
            @Node(DirectoryIndexer.class) Configuration config
        ) {
            return config.getOrThrow("batch_indexer", Configuration.class);
        }

        @Provides
        @Singleton
        public static Analyzer provideAnalyzer() {
            return new StandardAnalyzer();
        }
    }

    @Component.Builder
    interface Builder {

        @BindsInstance Builder config(
            @Configuration.Node(DirectoryIndexer.class)
            Configuration config
        );

        DirectoryIndexer build();
    }

    BatchIndexer indexer();

    DirectoryExtractor extractor();

    static void main(Configuration.Args args) throws Exception {

        Configuration config = Configuration.parse(args);

        DirectoryIndexer directoryIndexer = DaggerDirectoryIndexer.builder()
            .config(config)
            .build();

        DirectoryExtractor extractor = directoryIndexer.extractor();

        try (BatchIndexer indexer = directoryIndexer.indexer()) {
            extractor.extract((file, attrs) -> {
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
