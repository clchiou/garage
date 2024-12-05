package g1.base;

import java.util.Optional;

public class Optionals {

    private Optionals() {
        throw new AssertionError();
    }

    public static <T> Optional<T> flatten(Optional<Optional<T>> optional) {
        return optional.orElse(Optional.empty());
    }
}
