package g1.example.messaging;

import g1.base.ServerApp;
import g1.example.Books.Book;
import g1.example.Books.BookRequest;
import g1.example.Books.BookResponse;
import g1.messaging.reqrep.Server;
import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.capnproto.StructList;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.inject.Inject;
import javax.inject.Singleton;

@Singleton
public class BookServer implements Server {
    private static final Logger LOG = LoggerFactory.getLogger(
        BookServer.class
    );

    @Inject
    public BookServer() {
        // Do nothing here for now; this is for the Inject annotation.
    }

    public static void main(String[] args) {
        ServerApp.main(DaggerBookServerComponent.create(), args);
    }

    @Override
    public void serve(
        MessageReader request,
        MessageBuilder response
    ) throws Exception {
        BookRequest.Reader bookRequest = request.getRoot(BookRequest.factory);
        BookResponse.Builder bookResponse = response.initRoot(
            BookResponse.factory
        );
        BookRequest.Args.Reader args = bookRequest.getArgs();
        switch (args.which()) {
            case GET_BOOK:
                bookResponse.initResult().initGetBook().setId(42);
                break;
            case LIST_BOOKS:
                StructList.Builder<Book.Builder> books =
                    bookResponse.initResult().initListBooks(1);
                books.get(0).setId(42);
                break;
            default:
                LOG.atError()
                    .addArgument(args.which())
                    .log("unhandled request: {}");
                bookResponse.initError().initInternalError();
                break;
        }
    }
}
