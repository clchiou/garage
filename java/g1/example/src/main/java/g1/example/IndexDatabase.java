package g1.example;

import com.google.common.collect.ImmutableList;
import g1.base.Application;
import g1.base.Configuration;
import g1.base.ConfigurationLoader;
import g1.base.ConfiguredApp;
import g1.search.IndexWriters;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.TextField;
import org.apache.lucene.index.IndexWriter;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.Result;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.sql.Connection;
import java.sql.DriverManager;

import static g1.example.jooq.Tables.AUTHORS;
import static g1.example.jooq.Tables.BOOKS;

public class IndexDatabase extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(
        IndexDatabase.class
    );

    @Configuration
    public static String databaseUrl = "jdbc:sqlite::memory:";

    public static void main(String[] args) {
        Application.main(new IndexDatabase(), args);
    }

    @Override
    public void run() throws Exception {
        new ConfigurationLoader(ImmutableList.of("g1")).load(configPaths);
        IndexWriter writer = IndexWriters.open(new StandardAnalyzer());
        try (
            Connection connection = DriverManager.getConnection(databaseUrl)
        ) {
            DSLContext context = DSL.using(connection, SQLDialect.SQLITE);
            Result<Record> result = context
                .select()
                .from(BOOKS)
                .join(AUTHORS)
                .on(BOOKS.AUTHOR_ID.eq(AUTHORS.ID))
                .fetch();
            for (Record record : result) {
                index(writer, record);
            }
        } finally {
            IndexWriters.close(writer);
        }
    }

    private void index(IndexWriter writer, Record record) throws IOException {
        String title = record.getValue(BOOKS.TITLE);
        String author = record.getValue(AUTHORS.NAME);
        LOG.atInfo()
            .addArgument(title)
            .addArgument(author)
            .log("index: title=\"{}\" author=\"{}\"");
        Document doc = new Document();
        doc.add(new TextField("title", title, Field.Store.YES));
        doc.add(new TextField("author", author, Field.Store.YES));
        writer.addDocument(doc);
    }
}
