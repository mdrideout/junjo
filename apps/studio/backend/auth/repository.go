package auth

import (
	"context"
	"junjo-server/db"
	"junjo-server/db_gen"
)

// DbHasUsers checks if any users exist and returns a boolean.
func DbHasUsers(ctx context.Context) (bool, error) {
	queries := db_gen.New(db.DB)
	count, err := queries.CountUsers(ctx)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

func CreateUser(ctx context.Context, email string, password string) error {
	queries := db_gen.New(db.DB)
	_, err := queries.CreateUser(ctx, db_gen.CreateUserParams{
		Email:        email,
		PasswordHash: password,
	})
	if err != nil {
		return err
	}
	return nil
}
