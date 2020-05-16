package g1.example;

import com.google.common.collect.Lists;
import g1.base.Application;
import g1.example.Books.Book;
import org.capnproto.MessageReader;
import org.capnproto.Serialize;
import org.capnproto.Text;
import org.kohsuke.args4j.Argument;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.channels.ReadableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class DecodeCapnprotoMessage extends Application {
    private static final Logger LOG = LoggerFactory.getLogger(
        DecodeCapnprotoMessage.class
    );

    @Argument
    public List<Path> messagePaths = Lists.newArrayList();

    public static void main(String[] args) {
        Application.main(new DecodeCapnprotoMessage(), args);
    }

    @Override
    public void run() throws Exception {
        for (Path messagePath : messagePaths) {
            LOG.atInfo()
                .addArgument(messagePath)
                .log("decode message from: {}");
            try (
                ReadableByteChannel channel =
                    Files.newByteChannel(messagePath)
            ) {
                MessageReader message = Serialize.read(channel);
                Book.Reader book = message.getRoot(Book.factory);
                LOG.atInfo()
                    .addArgument(book.getId())
                    .addArgument(book.getTitle())
                    .addArgument(
                        StreamSupport
                            .stream(book.getAuthors().spliterator(), false)
                            .map(Text.Reader::toString)
                            .collect(Collectors.joining(", "))
                    )
                    .log("id = {} ; title = {} ; authors = {}");
            }
        }
    }
}
