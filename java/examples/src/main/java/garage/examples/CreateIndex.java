package garage.examples;

import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.LongPoint;
import org.apache.lucene.document.StringField;
import org.apache.lucene.document.TextField;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.index.Term;
import org.apache.lucene.store.FSDirectory;
import org.kohsuke.args4j.CmdLineException;
import org.kohsuke.args4j.CmdLineParser;
import org.kohsuke.args4j.Option;
import org.kohsuke.args4j.spi.PathOptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.FileVisitResult;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class CreateIndex {
    private static final Logger LOG =
        LoggerFactory.getLogger(CreateIndex.class);

    @Option(name = "--update", usage = "update index")
    private boolean doUpdate;

    @Option(name = "--docs", required = true,
            usage = "provide input docs directory")
    private Path docsDirPath;

    @Option(name = "--index", required = true,
            usage = "provide output index directory")
    private Path indexDirPath;

    public static void main(String[] args) throws Error, IOException {
        CreateIndex createIndex = null;
        try {
            createIndex = new CreateIndex(args);
        } catch (Error e) {
            if (e.getMessage() != null) {
                System.err.print(e.getMessage());
            }
            System.exit(1);
        }
        createIndex.index();
    }

    public static class Error extends Exception {
        Error(String message) { super(message); }
    }

    public CreateIndex(String[] args) throws Error {
        CmdLineParser parser = new CmdLineParser(this);
        try {
            parser.parseArgument(args);
        } catch (CmdLineException e) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try {
                new OutputStreamWriter(output)
                    .append(e.getMessage()).append('\n')
                    .close();
            } catch (IOException exc) {
                System.err.println(
                    "Err when writing error message: " + exc.getMessage());
            }
            parser.printUsage(output);
            throw new Error(output.toString());
        }
    }

    public void index() throws Error, IOException {
        if (!isReadableDirectory(docsDirPath)) {
            throw new Error("Not a readable directory: " + docsDirPath);
        }
        if (Files.exists(indexDirPath) && !isWritableDirectory(indexDirPath)) {
            throw new Error("Not a writable directory: " + indexDirPath);
        }

        LOG.info("start indexing {}", indexDirPath);
        long duration = System.nanoTime();

        Analyzer analyzer = new StandardAnalyzer();
        IndexWriterConfig config = new IndexWriterConfig(analyzer);

        config.setOpenMode(
            doUpdate ?
                IndexWriterConfig.OpenMode.CREATE_OR_APPEND :
                IndexWriterConfig.OpenMode.CREATE
        );

        // This is optional, but if we are indexing many documents,
        // increase this size and the JVM heap size.
        config.setRAMBufferSizeMB(256);

        IndexWriter writer = new IndexWriter(
            FSDirectory.open(indexDirPath),
            config
        );

        indexDocs(writer, docsDirPath);

        writer.forceMerge(1);

        writer.close();

        duration = System.nanoTime() - duration;
        LOG.info("create index in {} seconds", duration / 1e9d);
    }

    private static void indexDocs(
        IndexWriter writer, Path docsDirPath
    ) throws IOException {
        Files.walkFileTree(
            docsDirPath,
            new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs
                ) throws IOException {
                    try {
                        indexDoc(
                            writer,
                            file,
                            attrs.lastModifiedTime().toMillis()
                        );
                    } catch (IOException e) {
                        // At the moment, we just carry on.
                        LOG.warn("err when indexing {} due to {}", file, e);
                    }
                    return FileVisitResult.CONTINUE;
                }
            }
        );
    }

    private static void indexDoc(
        IndexWriter writer, Path docPath, long lastModified
    ) throws IOException {
        try (InputStream stream = Files.newInputStream(docPath)) {
            Document doc = new Document();

            doc.add(new StringField(
                "path",
                docPath.toString(),
                Field.Store.YES
            ));

            doc.add(new LongPoint("modified", lastModified));

            doc.add(new TextField(
                "contents",
                new BufferedReader(new InputStreamReader(
                    stream,
                    StandardCharsets.UTF_8
                ))
            ));

            if (writer.getConfig().getOpenMode() ==
                    IndexWriterConfig.OpenMode.CREATE) {
                LOG.info("add: {}", docPath);
                writer.addDocument(doc);
            } else {
                LOG.info("update: {}", docPath);
                writer.updateDocument(
                    new Term("path", docPath.toString()),
                    doc
                );
            }
        }
    }

    private static boolean isReadableDirectory(Path path) {
        return Files.isDirectory(path) && Files.isReadable(path);
    }

    private static boolean isWritableDirectory(Path path) {
        return Files.isDirectory(path) && Files.isWritable(path);
    }
}
