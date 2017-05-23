package garage.examples;

import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.queryparser.classic.QueryParser;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.Query;
import org.apache.lucene.search.ScoreDoc;
import org.apache.lucene.search.TopDocs;
import org.apache.lucene.store.FSDirectory;
import org.kohsuke.args4j.CmdLineException;
import org.kohsuke.args4j.CmdLineParser;
import org.kohsuke.args4j.Option;
import org.kohsuke.args4j.spi.PathOptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.file.Path;

public class SearchIndex {
    private static final Logger LOG =
        LoggerFactory.getLogger(SearchIndex.class);

    @Option(name = "--index", required = true,
            handler = PathOptionHandler.class,
            usage = "provide input index directory")
    private Path indexDirPath;

    @Option(name = "--field", usage = "search this field")
    private String field = "contents";

    @Option(name = "--query", required = true,
            usage = "provide search query")
    private String queryString;

    @Option(name = "--num-results", required = true,
            usage = "set num results")
    private int numResults;

    @Option(name = "--raw", usage = "output in raw format")
    private boolean outputRawFormat;

    public static void main(String[] args) throws Exception {
        SearchIndex searchIndex = null;
        try {
            searchIndex = new SearchIndex(args);
        } catch (Error e) {
            if (e.getMessage() != null) {
                System.err.print(e.getMessage());
            }
            System.exit(1);
        }
        searchIndex.search();
    }

    public static class Error extends Exception {
        Error(String message) { super(message); }
    }

    public SearchIndex(String[] args) throws Error {
        CmdLineParser parser = new CmdLineParser(this);
        try {
            parser.parseArgument(args);
        } catch (CmdLineException e) {
            ByteArrayOutputStream message = new ByteArrayOutputStream();
            try {
                new OutputStreamWriter(message)
                    .append(e.getMessage())
                    .append('\n')
                    .close();
            } catch (IOException exc) {
                System.err.println(
                    "Err when writing error message: " + exc.getMessage());
            }
            parser.printUsage(message);
            throw new Error(message.toString());
        }
    }

    public void search() throws Exception {
        try (IndexReader reader =
                DirectoryReader.open(FSDirectory.open(indexDirPath))) {

            Analyzer analyzer = new StandardAnalyzer();
            QueryParser parser = new QueryParser(field, analyzer);
            Query query = parser.parse(queryString);
            LOG.info("search for: {}", query.toString(field));

            IndexSearcher searcher = new IndexSearcher(reader);
            search(searcher, query);
        }
    }

    private void search(
        IndexSearcher searcher, Query query
    ) throws IOException {

        long duration = System.nanoTime();
        TopDocs results = searcher.search(query, numResults);
        duration = System.nanoTime() - duration;
        LOG.info("search index in {} seconds", duration / 1e9d);

        LOG.info("find {} matching documents", results.totalHits);
        for (ScoreDoc hit : results.scoreDocs) {
            if (outputRawFormat) {
                LOG.info("doc={} score={}", hit.doc, hit.score);
            } else {
                Document doc = searcher.doc(hit.doc);
                LOG.info(
                    "doc={} score={} path={}",
                    hit.doc, hit.score, doc.get("path")
                );
            }
        }
    }
}
