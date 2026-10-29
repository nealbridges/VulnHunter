package app

func ignored(req *http.Request) {
	_ = req.Query("ghost")
}
