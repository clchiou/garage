package g1.search;

import g1.base.Configuration;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.store.FSDirectory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static com.google.common.base.Preconditions.checkNotNull;

/**
 * Utilities of Lucene {@link IndexWriter}.
 */
public class IndexWriters {
    private static final Logger LOG = LoggerFactory.getLogger(
        IndexWriters.class
    );

    /**
     * Default index path.
     */
    @Configuration
    public static String indexPath = null;

    /**
     * Default RAM buffer size; Unit: MB.
     * <p>
     * Although theoretically setting it to a larger value might yield
     * higher batch indexing throughput, our measurements show that the
     * default throughput is already very impressive.  Also, a larger
     * value might cause JVM to OOM.  So it might not be worthwhile to
     * increase this value.
     */
    @Configuration
    public static double ramBufferSize =
        IndexWriterConfig.DEFAULT_RAM_BUFFER_SIZE_MB;

    /**
     * Flush after the number of buffered doc exceeds the limit.
     * <p>
     * We use Lucene's default for the same reason stated in
     * {@code ramBufferSize} above.
     */
    @Configuration
    public static int maxBufferedDocs =
        IndexWriterConfig.DEFAULT_MAX_BUFFERED_DOCS;

    /**
     * Whether to force merge in {@link #close(IndexWriter)}.
     */
    @Configuration
    public static boolean forceMerge = true;

    private IndexWriters() {
        throw new AssertionError();
    }

    /**
     * Detect mode and open an {@link IndexWriter}.
     */
    public static IndexWriter open(Analyzer analyzer) throws IOException {
        return open(Paths.get(checkNotNull(indexPath)), analyzer);
    }

    /**
     * Detect mode and open an {@link IndexWriter}.
     */
    public static IndexWriter open(
        Path indexPath, Analyzer analyzer
    ) throws IOException {
        return Files.exists(indexPath) ?
            append(indexPath, analyzer) : create(indexPath, analyzer);
    }

    /**
     * Open an {@link IndexWriter} in {@code CREATE} mode.
     */
    public static IndexWriter create(
        Path indexPath, Analyzer analyzer
    ) throws IOException {
        LOG.atInfo().addArgument(indexPath).log("create index writer on {}");
        return open(indexPath, analyzer, IndexWriterConfig.OpenMode.CREATE);
    }

    /**
     * Open an {@link IndexWriter} in {@code APPEND} mode.
     */
    public static IndexWriter append(
        Path indexPath, Analyzer analyzer
    ) throws IOException {
        LOG.atInfo().addArgument(indexPath).log("append index writer on {}");
        return open(indexPath, analyzer, IndexWriterConfig.OpenMode.APPEND);
    }

    private static IndexWriter open(
        Path indexPath, Analyzer analyzer, IndexWriterConfig.OpenMode mode
    ) throws IOException {
        return new IndexWriter(
            FSDirectory.open(indexPath),
            applyConfig(new IndexWriterConfig(analyzer).setOpenMode(mode))
        );
    }

    public static IndexWriterConfig applyConfig(IndexWriterConfig config) {
        LOG.atInfo()
            .addArgument(ramBufferSize)
            .log("set RAM buffer size: {} MB");
        config.setRAMBufferSizeMB(ramBufferSize);
        LOG.atInfo()
            .addArgument(maxBufferedDocs)
            .log("set max buffered docs: {}");
        config.setMaxBufferedDocs(maxBufferedDocs);
        return config;
    }

    public static void close(IndexWriter writer) throws IOException {
        LOG.atInfo()
            .addArgument(writer.getDirectory())
            .log("close index writer on {}");
        if (forceMerge) {
            writer.forceMerge(/* maxNumSegments */ 1);
        }
        writer.close();
    }
}
