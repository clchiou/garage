package g1.example.etcd;

import g1.base.Configuration;
import g1.base.ServerApp;
import g1.etcd.Controller;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Nullable;
import javax.inject.Inject;

public class Watch implements Controller<String> {
    private static final Logger LOG = LoggerFactory.getLogger(Watch.class);

    @Configuration
    public static String key = null;

    @Inject
    public Watch() {
    }

    public static void main(String[] args) {
        ServerApp.main(DaggerWatchComponent.create(), args);
    }

    @Override
    public Class<String> clazz() {
        return String.class;
    }

    @Override
    public void control(String key, @Nullable String data) {
        LOG.atInfo().addArgument(key).addArgument(data).log("watch: {} {}");
    }
}
