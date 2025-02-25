package schema

import "entgo.io/ent"

// Todo holds the schema definition for the Todo entity.
type Todo struct {
	ent.Schema
}

// Fields of the Todo.
func (Todo) Fields() []ent.Field {
	return nil
}

// Edges of the Todo.
func (Todo) Edges() []ent.Edge {
	return nil
}
