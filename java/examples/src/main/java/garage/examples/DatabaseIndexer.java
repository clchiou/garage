package garage.examples;

import com.google.common.base.Preconditions;
import dagger.Component;
import org.apache.lucene.index.IndexWriterConfig.OpenMode;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.Result;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;

import javax.inject.Singleton;

import java.sql.Connection;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.Configuration.Args;
import garage.base.DatabaseModule;
import garage.search.analyzer.StandardAnalyzerModule;
import garage.search.indexer.BatchIndexer;

import static garage.examples.Tables.*;

@Component(
    modules = {
        DatabaseModule.class,
        StandardAnalyzerModule.class,
    }
)
@Singleton
public interface DatabaseIndexer {

    @Component.Builder
    interface Builder extends
        DatabaseModule.DaggerBuilderMixin<Builder>,
        BatchIndexer.DaggerBuilderMixin<Builder>
    {
        DatabaseIndexer build();
    }

    Connection connection();

    BatchIndexer indexer();

    static void main(Args args) throws Exception {

        Configuration config = Configuration.parse(args);

        DatabaseIndexer databaseIndexer = DaggerDatabaseIndexer.builder()
            .databaseConfig(
                config.getOrThrow("database", Configuration.class))
            .batchIndexerConfig(
                config.getOrThrow("batch_indexer", Configuration.class))
            .build();

        try (
            Connection connection = databaseIndexer.connection();
            BatchIndexer indexer = databaseIndexer.indexer()
        ) {

            Preconditions.checkState(
                indexer.getOpenMode() == OpenMode.CREATE,
                "do not support non-CREATE open mode at the moment"
            );

            DSLContext context = DSL.using(connection, SQLDialect.SQLITE);
            Result<Record> result = context.select().from(BOOKS).fetch();
            for (Record record : result) {
                // TODO...
            }
        }
    }

    static void main(String[] args) {
        Application.run(args, new Args(), DatabaseIndexer::main);
    }
}
