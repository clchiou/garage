package g1.example.msg;

import g1.base.Configuration;
import g1.base.ServerApp;

public class BookServer {

    @Configuration
    public static String url = null;

    @Configuration
    public static int parallelism = 1;

    public static void main(String[] args) {
        ServerApp.main(DaggerBookServerComponent.create(), args);
    }
}
