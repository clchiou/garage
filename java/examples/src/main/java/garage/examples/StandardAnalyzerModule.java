package garage.examples;

import dagger.Module;
import dagger.Provides;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.standard.StandardAnalyzer;

import javax.inject.Singleton;

@Module
public class StandardAnalyzerModule {

    @Provides
    @Singleton
    public static Analyzer provideAnalyzer() {
        return new StandardAnalyzer();
    }
}
