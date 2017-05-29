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
import org.kohsuke.args4j.Option;
import org.kohsuke.args4j.spi.PathOptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Path;

import garage.base.Application;

public class SearchIndex {

    private static final Logger LOG =
        LoggerFactory.getLogger(SearchIndex.class);

    private SearchIndex() {
        throw new AssertionError();
    }

    private static class Args extends Application.Args {

        @Option(name = "--index", required = true,
            handler = PathOptionHandler.class,
            usage = "provide input index directory")
        private Path indexDirPath;

        @Option(name = "--field", usage = "search this field")
        private String field = "contents";

        @Option(name = "--query", required = true,
            usage = "provide search query")
        private String query;

        @Option(name = "--num-results", required = true,
            usage = "set num results")
        private int numResults;
    }

    public static void main(String[] args) {
        Application.run(args, new Args(), SearchIndex::search);
    }

    private static void search(Args args) throws Exception {
        try (IndexReader reader =
                DirectoryReader.open(FSDirectory.open(args.indexDirPath))) {

            Analyzer analyzer = new StandardAnalyzer();
            QueryParser parser = new QueryParser(args.field, analyzer);
            Query query = parser.parse(args.query);
            LOG.info("search for: {}", query.toString(args.field));

            IndexSearcher searcher = new IndexSearcher(reader);
            search(args, searcher, query);
        }
    }

    private static void search(
        Args args,
        IndexSearcher searcher, Query query
    ) throws IOException {
        long duration = System.nanoTime();
        TopDocs results = searcher.search(query, args.numResults);
        duration = System.nanoTime() - duration;
        LOG.info("search index in {} seconds", duration / 1e9d);

        LOG.info("find {} matching documents", results.totalHits);
        for (ScoreDoc hit : results.scoreDocs) {
            Document doc = searcher.doc(hit.doc);
            LOG.info(
                "doc={} score={} path={}",
                hit.doc, hit.score, doc.get("path")
            );
        }
    }
}
