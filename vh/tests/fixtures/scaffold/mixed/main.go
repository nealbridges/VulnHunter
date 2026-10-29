package main

func mixedGo(r *http.Request) {
	_ = r.URL.Query().Get("q")
}
