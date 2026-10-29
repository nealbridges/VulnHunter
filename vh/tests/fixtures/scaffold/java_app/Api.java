package app;

public class Api {
    @GetMapping("/users/{userId}")
    public String users(@RequestParam(value = "fullName") String fullName,
                        @PathVariable Long userId) {
        return fullName;
    }

    @PostMapping(path = "/login")
    public String login(@RequestBody LoginBody body) {
        return "";
    }

    @PostMapping("/upload")
    public String upload(@RequestParam("file") MultipartFile file,
                         @RequestPart(name = "meta") MultipartFile meta) {
        return "";
    }

    @RequestMapping("/payload/{kind}")
    public String payload(@RequestBody Payload body,
                          @RequestHeader("X-Key") String key,
                          @CookieValue("session") String session) {
        return "";
    }

    public String misc(HttpServletRequest request) {
        String a = request.getParameter("alpha");
        String b = request.getParameterValues("beta")[0];
        String c = request.getHeader("X-Trace");
        String d = System.getenv("HOME");
        return a + b + c + d;
    }

    @Value("${app.mode}")
    private String mode;

    @PostMapping("/missing")
    public String missing(@RequestBody MissingBody body) {
        return "";
    }

    @GetMapping("/bare")
    public String bare(@RequestParam String bareName) {
        return bareName;
    }
}
