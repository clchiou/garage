package g1.example;

import com.google.common.collect.ImmutableList;
import g1.base.Application;
import g1.base.Configuration;
import g1.base.ConfigurationLoader;
import g1.base.ConfiguredApp;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.Result;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.Connection;
import java.sql.DriverManager;

import static g1.example.jooq.Tables.AUTHORS;
import static g1.example.jooq.Tables.BOOKS;

public class DumpDatabase extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(
        DumpDatabase.class
    );

    @Configuration
    public static String databaseUrl = "jdbc:sqlite::memory:";

    public static void main(String[] args) {
        Application.main(new DumpDatabase(), args);
    }

    @Override
    public void run() throws Exception {
        new ConfigurationLoader(ImmutableList.of("g1")).load(configPaths);
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
                LOG.atInfo()
                    .addArgument(record.getValue(BOOKS.TITLE))
                    .addArgument(record.getValue(AUTHORS.NAME))
                    .log("book title: \"{}\" ; author: \"{}\"");
            }
        }
    }
}
