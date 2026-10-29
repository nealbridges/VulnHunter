package app

func routes(r *mux.Router) {
	r.HandleFunc("/users/{id}", handleSearch)
	r.GET("/items/{itemId:[0-9]+}", handleSearch)
	r.POST("/files/{filePath...}", handleSearch)
	r.DELETE("/legacy/:legacyId", handleSearch)
	v := mux.Vars(r)
	_ = v["tenant"]
}

type ignored struct {
	Field string
}
