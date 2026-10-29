package testdata

func ignored(r *http.Request) {
	_ = r.Query("ghost")
}
