package libv2ray;

/**
 * ЗАГЛУШКА API AndroidLibXrayLite (только для флейвора stub).
 * Соответствует Go-интерфейсу CoreCallbackHandler (методы возвращают int → long).
 */
public interface CoreCallbackHandler {
    long startup();
    long shutdown();
    long onEmitStatus(long code, String msg);
}
