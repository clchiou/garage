package garage.search.indexer;

import com.google.common.base.Preconditions;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.index.Term;
import org.apache.lucene.store.FSDirectory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import garage.base.Configuration;
import garage.base.MoreFiles;

public class BatchIndexer implements AutoCloseable {

    private static final Logger LOG =
        LoggerFactory.getLogger(BatchIndexer.class);

    // By default, we create a new index.
    public static final String OPEN_MODE =
        IndexWriterConfig.OpenMode.CREATE.name();

    // Default RAM buffer size. Unit: MB.
    public static final double RAM_BUFFER_SIZE = 1024.0d;

    // By default flush is not triggered by the number of buffered docs,
    // but by the buffer size; this should yield better batch index
    // throughput.
    public static final int MAX_BUFFERED_DOCS =
        IndexWriterConfig.DISABLE_AUTO_FLUSH;

    private final IndexWriter writer;
    private final IndexWriterConfig.OpenMode mode;

    @Inject
    public BatchIndexer(Configuration config, Analyzer analyzer) {
        IndexWriterConfig writerConfig = new IndexWriterConfig(analyzer);

        String openMode = config.get("open_mode", String.class)
            .orElse(OPEN_MODE);
        mode = IndexWriterConfig.OpenMode.valueOf(openMode);
        LOG.info("set index open mode: {}", mode);
        writerConfig.setOpenMode(mode);

        double ramBufferSize = config.get("ram_buffer_size", Double.class)
            .orElse(RAM_BUFFER_SIZE);
        LOG.info("set RAM buffer size: {} MB", ramBufferSize);
        writerConfig.setRAMBufferSizeMB(ramBufferSize);

        int maxBufferedDocs = config.get("max_buffered_docs", Integer.class)
            .orElse(MAX_BUFFERED_DOCS);
        LOG.info("set max buffered docs: {}", maxBufferedDocs);
        writerConfig.setMaxBufferedDocs(maxBufferedDocs);

        Path index = Paths.get(config.getOrThrow("index", String.class));
        // Make sure index directory agrees with open mode.
        switch (mode) {
            case CREATE:
                Preconditions.checkArgument(
                    !Files.exists(index),
                    "refuse to overwrite index: %s", index
                );
                break;
            case CREATE_OR_APPEND:
                Preconditions.checkArgument(
                    !Files.exists(index) ||
                        MoreFiles.isWritableDirectory(index),
                    "index is not writable: %s", index
                );
                break;
            case APPEND:
                Preconditions.checkArgument(
                    MoreFiles.isWritableDirectory(index),
                    "index is not writable or does not exist: %s", index
                );
                break;
            default:
                throw new AssertionError(mode);
        }

        try {
            LOG.info("open index: {}", index);
            writer = new IndexWriter(FSDirectory.open(index), writerConfig);
        } catch (IOException e) {
            // Dagger does not support checked exception on @Inject
            // constructor; let's turn it into RuntimeError.
            throw new RuntimeException(e);
        }
    }

    public long index(Document doc) throws IOException {
        Preconditions.checkState(mode == IndexWriterConfig.OpenMode.CREATE);
        long seq = writer.addDocument(doc);
        LOG.info("index: doc sequence number {}", seq);
        return seq;
    }

    public long index(Iterable<Document> docs) throws IOException {
        Preconditions.checkState(mode == IndexWriterConfig.OpenMode.CREATE);
        long seq = writer.addDocuments(docs);
        LOG.info("index many: doc sequence number {}", seq);
        return seq;
    }

    public long index(Term id, Document doc) throws IOException {
        Preconditions.checkState(mode != IndexWriterConfig.OpenMode.CREATE);
        long seq = writer.updateDocument(id, doc);
        LOG.info("index update: doc sequence number {}", seq);
        return seq;
    }

    @Override
    public void close() throws Exception {
        LOG.info("merge index segments");
        writer.forceMerge(1);

        writer.close();
        LOG.info("complete indexing to {}", writer.getDirectory());
    }
}
