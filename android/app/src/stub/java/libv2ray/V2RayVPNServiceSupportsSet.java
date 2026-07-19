package libv2ray;

/**
 * ЗАГЛУШКА API AndroidLibXrayLite (только для флейвора stub).
 * Сигнатуры соответствуют реальному gomobile-интерфейсу: методы с Go error →
 * Java void ... throws Exception.
 */
public interface V2RayVPNServiceSupportsSet {
    void setup(String conf) throws Exception;
    void prepare() throws Exception;
    void shutdown() throws Exception;
    boolean protect(long fd);
    long onEmitStatus(long code, String msg);
    void sendFd() throws Exception;
}
