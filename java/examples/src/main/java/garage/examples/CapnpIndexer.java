package garage.examples;

import com.google.common.base.Preconditions;
import dagger.Component;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.TextField;
import org.apache.lucene.index.IndexWriterConfig.OpenMode;
import org.capnproto.MessageReader;
import org.capnproto.SerializePacked;
import org.capnproto.Text;

import javax.inject.Singleton;
import java.nio.channels.ReadableByteChannel;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.Configuration.Args;
import garage.search.analyzer.StandardAnalyzerModule;
import garage.search.indexer.BatchIndexer;

import static garage.examples.Books.*;

@Component(modules = {StandardAnalyzerModule.class})
@Singleton
public interface CapnpIndexer {

    @Component.Builder
    interface Builder extends BatchIndexer.DaggerBuilderMixin<Builder> {
        CapnpIndexer build();
    }

    BatchIndexer indexer();

    static void main(Args args) throws Exception {

        Configuration config = Configuration.parse(args);

        CapnpIndexer capnpIndexer = DaggerCapnpIndexer.builder()
            .batchIndexerConfig(
                config.getOrThrow("batch_indexer", Configuration.class))
            .build();

        try (
            ReadableByteChannel channel = Files.newByteChannel(
                Paths.get(config.getOrThrow("input_path", String.class)),
                StandardOpenOption.READ);
            BatchIndexer indexer = capnpIndexer.indexer()
        ) {

            Preconditions.checkState(
                indexer.getOpenMode() == OpenMode.CREATE,
                "do not support non-CREATE open mode at the moment"
            );

            MessageReader message =
                SerializePacked.readFromUnbuffered(channel);
            Book.Reader book = message.getRoot(Book.factory);

            Document doc = new Document();
            if (book.hasTitle()) {
                doc.add(new TextField(
                    "title",
                    book.getTitle().toString(),
                    Field.Store.YES
                ));
            }
            if (book.hasAuthors()) {
                for (Text.Reader author : book.getAuthors()) {
                    doc.add(new TextField(
                        "author",
                        author.toString(),
                        Field.Store.YES
                    ));
                }
            }
            indexer.index(doc);
        }
    }

    static void main(String[] args) {
        Application.run(args, new Args(), CapnpIndexer::main);
    }
}
