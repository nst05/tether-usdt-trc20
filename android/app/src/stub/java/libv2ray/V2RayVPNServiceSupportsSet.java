package libv2ray;

/**
 * ЗАГЛУШКА API AndroidLibXrayLite (только для флейвора stub).
 * В флейворе full этот интерфейс приходит из настоящего libv2ray.aar.
 */
public interface V2RayVPNServiceSupportsSet {
    long setup(String conf);
    long shutdown();
    boolean protect(long fd);
    long onEmitStatus(long code, String msg);
    long prepare();
    long sendFd();
}
