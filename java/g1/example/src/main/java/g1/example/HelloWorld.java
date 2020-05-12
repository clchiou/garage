package g1.example;

import g1.base.Application;

public class HelloWorld extends Application {

    public static void main(String[] args) {
        Application.main(new HelloWorld(), args);
    }

    @Override
    public void run() throws Exception {
        System.out.println("Hello, world!");
    }
}
