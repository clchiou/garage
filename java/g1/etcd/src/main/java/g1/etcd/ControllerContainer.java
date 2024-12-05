package g1.etcd;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.util.concurrent.AbstractExecutionThreadService;
import g1.base.Names;
import io.etcd.jetcd.ByteSequence;
import io.etcd.jetcd.Client;
import io.etcd.jetcd.KV;
import io.etcd.jetcd.Watch;
import io.etcd.jetcd.Watch.Watcher;
import io.etcd.jetcd.kv.GetResponse;
import io.etcd.jetcd.options.WatchOption;
import io.etcd.jetcd.watch.WatchEvent;
import io.etcd.jetcd.watch.WatchEvent.EventType;
import io.etcd.jetcd.watch.WatchResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.function.Consumer;

import static g1.etcd.ByteSequences.from;
import static g1.etcd.ByteSequences.to;

class ControllerContainer extends AbstractExecutionThreadService {
    private static final Logger LOG = LoggerFactory.getLogger(ControllerContainer.class);

    private static final Names NAMES = new Names("controller");

    private static final ObjectMapper MAPPER = new ObjectMapper();

    static {
        MAPPER.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    private final String name;
    private final Client client;
    private final ByteSequence targetKey;
    private final WatchOption option;
    private final BlockingQueue<Optional<WatchResponse>> responses;
    private final Consumer<KeyValue> controller;

    // TODO: For now we only watch a single key.
    private ControllerContainer(Client client, String targetKey, Consumer<KeyValue> controller) {
        super();

        this.name = NAMES.next();

        this.client = client;
        this.targetKey = from(targetKey);
        // It also seems nice to set `withProgressNotify`.
        this.option = WatchOption.builder().withCreateNotify(true).withProgressNotify(true).build();

        this.responses = new ArrayBlockingQueue<>(64, /* fair */ true);
        this.controller = controller;
    }

    static <T> ControllerContainer make(Client client, String targetKey, Controller<T> controller) {
        return new ControllerContainer(client, targetKey, adapt(controller));
    }

    private static <T> Consumer<KeyValue> adapt(Controller<T> controller) {
        return kv -> {
            // It appears that `ByteSequence.toString(UTF_8)` never fails.
            String key = to(kv.key);
            String value = kv.value == null ? null : to(kv.value);

            T data = null;
            try {
                if (value != null) {
                    data = MAPPER.readValue(value, controller.clazz());
                }
            } catch (Exception e) {
                LOG.atWarn()
                    .addArgument(key)
                    .addArgument(value)
                    .setCause(e)
                    .log("decode error: {} {}");
                return;
            }

            try {
                controller.control(key, data);
            } catch (Exception e) {
                LOG.atError()
                    .addArgument(key)
                    .addArgument(data)
                    .setCause(e)
                    .log("uncaught controller error: {} {}");
            }
        };
    }

    @Override
    @Nonnull
    protected String serviceName() {
        return name;
    }

    @Override
    protected void run() throws Exception {
        try (Watch watch = client.getWatchClient()) {
            // It appears that we cannot block the watch response consumer, such as by calling
            // `client.getKVClient().kv.get(...).get()`, so we defer the response handling.
            try (Watcher ignored = watch.watch(targetKey, option, response -> {
                if (!responses.offer(Optional.of(response))) {
                    LOG.atError().log("response queue is full");
                }
            })) {
                while (isRunning()) {
                    Optional<WatchResponse> response = responses.take();
                    if (response.isPresent()) {
                        handle(response.get());
                    } else {
                        break;
                    }
                }
            }
        }
    }

    private void handle(WatchResponse response) {
        if (response.isCreatedNotify()) {
            try (KV kv = client.getKVClient()) {
                GetResponse r = null;
                try {
                    r = kv.get(targetKey).get();
                } catch (Exception e) {
                    LOG.atWarn().setCause(e).log("kv.get error");
                }
                if (r != null && !r.getKvs().isEmpty()) {
                    controller.accept(new KeyValue(
                        r.getKvs().get(0).getKey(),
                        r.getKvs().get(0).getValue()
                    ));
                }
            }
        }

        for (WatchEvent event : response.getEvents()) {
            EventType type = event.getEventType();
            ByteSequence key = event.getKeyValue().getKey();
            ByteSequence value = event.getKeyValue().getValue();
            if (type == EventType.PUT) {
                // Keep `value`.
            } else if (type == EventType.DELETE) {
                value = null;
            } else {
                LOG.atWarn()
                    .addArgument(type)
                    .addArgument(key)
                    .addArgument(value)
                    .log("unrecognized event type: {} {} {}");
                continue;
            }
            controller.accept(new KeyValue(key, value));
        }
    }

    @Override
    protected void triggerShutdown() {
        try {
            responses.put(Optional.empty());
        } catch (InterruptedException e) {
            LOG.atError().setCause(e).log("fail to trigger shutdown");
        }
    }

    private record KeyValue(ByteSequence key, @Nullable ByteSequence value) {
    }
}
