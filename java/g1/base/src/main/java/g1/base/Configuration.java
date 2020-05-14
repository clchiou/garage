package g1.base;

import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

/**
 * Annotate a static field of configuration data.
 */
@Retention(RUNTIME)
@Target({FIELD})
public @interface Configuration {
}
