package garage.examples;

import com.google.common.base.Preconditions;
import dagger.Component;
import dagger.Module;
import dagger.Provides;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.LongPoint;
import org.apache.lucene.document.StringField;
import org.apache.lucene.document.TextField;
import org.apache.lucene.index.IndexWriterConfig.OpenMode;

import javax.inject.Singleton;

import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Paths;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.Configuration.Args;
import garage.search.extractor.DirectoryExtractor;
import garage.search.indexer.BatchIndexer;

@Component(
    modules = {
        StandardAnalyzerModule.class,
        DirectoryIndexer.DirectoryIndexerModule.class,
    }
)
@Singleton
public interface DirectoryIndexer {

    @Module
    class DirectoryIndexerModule {
        @Provides
        public static DirectoryExtractor.Predicate providePredicate() {
            return null;  // Filter out nothing.
        }
    }

    @Component.Builder
    interface Builder extends
        DirectoryExtractor.DaggerBuilderMixin<Builder>,
        BatchIndexer.DaggerBuilderMixin<Builder>
    {
        DirectoryIndexer build();
    }

    DirectoryExtractor extractor();

    BatchIndexer indexer();

    static void main(Args args) throws Exception {

        Configuration config = Configuration.parse(args);

        DirectoryIndexer directoryIndexer = DaggerDirectoryIndexer.builder()
            .directoryExtractorRoot(
                Paths.get(config.getOrThrow("root", String.class)))
            .batchIndexerConfig(
                config.getOrThrow("batch_indexer", Configuration.class))
            .build();

        DirectoryExtractor extractor = directoryIndexer.extractor();

        try (BatchIndexer indexer = directoryIndexer.indexer()) {

            Preconditions.checkState(
                indexer.getOpenMode() == OpenMode.CREATE,
                "do not support non-CREATE open mode at the moment"
            );

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
        Application.run(args, new Args(), DirectoryIndexer::main);
    }
}
