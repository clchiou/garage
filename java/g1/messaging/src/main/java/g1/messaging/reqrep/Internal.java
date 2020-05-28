package g1.messaging.reqrep;

import javax.inject.Qualifier;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;

import static java.lang.annotation.RetentionPolicy.RUNTIME;

/**
 * Qualifier for internal dependencies.
 */
@Qualifier
@Documented
@Retention(RUNTIME)
@interface Internal {
}
