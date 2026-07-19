package libv2ray;

/**
 * ЗАГЛУШКА API AndroidLibXrayLite (только для флейвора stub).
 * Сигнатуры соответствуют реальному gomobile-интерфейсу (методы возвращают
 * long/boolean, как их использует v2rayNG).
 */
public interface V2RayVPNServiceSupportsSet {
    long setup(String conf);
    long prepare();
    long shutdown();
    boolean protect(long fd);
    long onEmitStatus(long code, String msg);
    long sendFd();
}
