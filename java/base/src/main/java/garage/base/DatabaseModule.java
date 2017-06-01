package garage.base;

import dagger.BindsInstance;
import dagger.Module;
import dagger.Provides;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

import garage.base.Configuration.Node;

@Module
public class DatabaseModule {

    public interface DaggerBuilderMixin<T> {
        @BindsInstance
        T databaseConfig(@Node(DatabaseModule.class) Configuration config);
    }

    @Provides
    public static Connection provideConnection(
        @Node(DatabaseModule.class) Configuration config
    ) {
        try {
            return DriverManager.getConnection(
                config.getOrThrow("url", String.class));
        } catch (SQLException e) {
            // Dagger doesn't like checked exception.
            throw new RuntimeException(e);
        }
    }
}
