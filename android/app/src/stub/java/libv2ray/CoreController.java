package libv2ray;

/** ЗАГЛУШКА (флейвор stub). В full приходит из libv2ray.aar. */
public class CoreController {
    private boolean running = false;
    private final CoreCallbackHandler handler;

    public CoreController(CoreCallbackHandler handler) {
        this.handler = handler;
    }

    /** gomobile-геттер для экспортированного поля IsRunning. */
    public boolean getIsRunning() {
        return running;
    }

    public void startLoop(String configContent, int tunFd) throws Exception {
        running = true;
        if (handler != null) {
            handler.startup();
            handler.onEmitStatus(0, "Started successfully, running");
        }
    }

    public void stopLoop() throws Exception {
        running = false;
        if (handler != null) handler.shutdown();
    }
}
