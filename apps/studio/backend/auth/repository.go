package auth

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
)

// UsersExist checks if any users exist and returns a boolean.
func UsersExist(ctx context.Context) (bool, error) {
	queries := db_gen.New(db.DB)
	count, err := queries.CountUsers(ctx)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}
