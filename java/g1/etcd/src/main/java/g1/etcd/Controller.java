package g1.etcd;

import javax.annotation.Nullable;

public interface Controller<T> {

    Class<T> clazz();

    void control(String key, @Nullable T data) throws Exception;
}
