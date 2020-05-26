package g1.base;

import com.google.common.util.concurrent.Service;

import java.util.Set;

/**
 * Server component.
 * <p>
 * User should extends this interface and adds Dagger annotations to the
 * application-specific interface.
 */
public interface ServerComponent {

    /**
     * Provide {@link ConfigurationLoader} namespaces.
     * <p>
     * NOTE: It returns a set, not a list; this difference should be
     * irrelevant for now.
     */
    Set<String> namespaces();

    /**
     * Provide services.
     * <p>
     * We expect user to use Dagger's multi-bindings feature to inject
     * services into this set.
     */
    Set<Service> services();
}
