//! RFC 6902 JSON Patch replay for Store transitions.
//!
//! A patch is applied to a copy, so a failed patch changes nothing. The
//! `test` operation and every comparison use [`values_equal`], because RFC
//! 6902 compares numbers by value and the producers compute patches with the
//! same rule.

use crate::json::{Json, JsonObject, get, values_equal};

/// Apply every operation in order and return the patched document.
pub fn apply_patch(document: &Json, patch: &[Json]) -> Result<Json, String> {
    // Every operation is checked before the first one runs.
    let operations = patch
        .iter()
        .enumerate()
        .map(|(index, operation)| {
            Operation::parse(operation).map_err(|error| format!("operation {index}: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()?;

    let mut document = document.clone();
    for (index, operation) in operations.iter().enumerate() {
        operation
            .apply(&mut document)
            .map_err(|error| format!("operation {index}: {error}"))?;
    }
    Ok(document)
}

/// One reference token sequence from an RFC 6901 JSON Pointer.
type Pointer = Vec<String>;

enum Operation<'a> {
    Add { path: Pointer, value: &'a Json },
    Remove { path: Pointer },
    Replace { path: Pointer, value: &'a Json },
    Move { from: Pointer, path: Pointer },
    Copy { from: Pointer, path: Pointer },
    Test { path: Pointer, value: &'a Json },
}

impl<'a> Operation<'a> {
    fn parse(operation: &'a Json) -> Result<Self, String> {
        let operation = operation
            .as_object()
            .ok_or("an operation must be an object")?;
        let name = get(operation, "op")
            .as_str()
            .ok_or("an operation must have an \"op\" member")?;
        let path = pointer_member(operation, "path")?;
        let value = || {
            operation
                .get("value")
                .ok_or_else(|| format!("\"{name}\" must have a \"value\" member"))
        };
        match name {
            "add" => Ok(Self::Add {
                path,
                value: value()?,
            }),
            "remove" => Ok(Self::Remove { path }),
            "replace" => Ok(Self::Replace {
                path,
                value: value()?,
            }),
            "move" => Ok(Self::Move {
                from: pointer_member(operation, "from")?,
                path,
            }),
            "copy" => Ok(Self::Copy {
                from: pointer_member(operation, "from")?,
                path,
            }),
            "test" => Ok(Self::Test {
                path,
                value: value()?,
            }),
            other => Err(format!("unknown operation \"{other}\"")),
        }
    }

    fn apply(&self, document: &mut Json) -> Result<(), String> {
        match self {
            Self::Add { path, value } => add(document, path, (*value).clone()),
            Self::Remove { path } => remove(document, path).map(drop),
            Self::Replace { path, value } => {
                *resolve_mut(document, path)? = (*value).clone();
                Ok(())
            }
            Self::Move { from, path } => {
                if from == path {
                    // The value must still exist for the move to be valid.
                    return resolve(document, from).map(drop);
                }
                if path.starts_with(from) {
                    return Err("a value cannot be moved into one of its own children".to_string());
                }
                let value = remove(document, from)?;
                add(document, path, value)
            }
            Self::Copy { from, path } => {
                let value = resolve(document, from)?.clone();
                add(document, path, value)
            }
            Self::Test { path, value } => {
                let found = resolve(document, path)?;
                if values_equal(found, value) {
                    Ok(())
                } else {
                    Err("the tested value is not equal".to_string())
                }
            }
        }
    }
}

fn pointer_member(operation: &JsonObject, member: &str) -> Result<Pointer, String> {
    let text = get(operation, member)
        .as_str()
        .ok_or_else(|| format!("an operation must have a string \"{member}\" member"))?;
    parse_pointer(text)
}

fn parse_pointer(text: &str) -> Result<Pointer, String> {
    if text.is_empty() {
        return Ok(Vec::new());
    }
    let Some(tokens) = text.strip_prefix('/') else {
        return Err(format!("\"{text}\" is not a JSON Pointer"));
    };
    // `~1` is decoded before `~0`, so `~01` reads as `~1` and not `/`.
    Ok(tokens
        .split('/')
        .map(|token| token.replace("~1", "/").replace("~0", "~"))
        .collect())
}

/// An array index token: `0`, or digits with no leading zero.
fn array_index(token: &str) -> Result<usize, String> {
    let canonical = token == "0"
        || (!token.is_empty()
            && !token.starts_with('0')
            && token.bytes().all(|byte| byte.is_ascii_digit()));
    canonical
        .then(|| token.parse().ok())
        .flatten()
        .ok_or_else(|| format!("\"{token}\" is not an array index"))
}

fn resolve<'a>(document: &'a Json, path: &[String]) -> Result<&'a Json, String> {
    let mut current = document;
    for token in path {
        current = match current {
            Json::Object(members) => members.get(token),
            Json::Array(items) => items.get(array_index(token)?),
            _ => None,
        }
        .ok_or_else(|| format!("\"{token}\" does not exist"))?;
    }
    Ok(current)
}

fn resolve_mut<'a>(document: &'a mut Json, path: &[String]) -> Result<&'a mut Json, String> {
    let mut current = document;
    for token in path {
        current = match current {
            Json::Object(members) => members.get_mut(token),
            Json::Array(items) => items.get_mut(array_index(token)?),
            _ => None,
        }
        .ok_or_else(|| format!("\"{token}\" does not exist"))?;
    }
    Ok(current)
}

fn add(document: &mut Json, path: &[String], value: Json) -> Result<(), String> {
    let Some((last, parent)) = path.split_last() else {
        *document = value;
        return Ok(());
    };
    match resolve_mut(document, parent)? {
        Json::Object(members) => {
            members.insert(last.clone(), value);
            Ok(())
        }
        Json::Array(items) => {
            if last == "-" {
                items.push(value);
                return Ok(());
            }
            let index = array_index(last)?;
            if index > items.len() {
                return Err(format!("index {index} is outside the array"));
            }
            items.insert(index, value);
            Ok(())
        }
        _ => Err(format!("\"{last}\" cannot be added to a scalar")),
    }
}

fn remove(document: &mut Json, path: &[String]) -> Result<Json, String> {
    let Some((last, parent)) = path.split_last() else {
        return Err("the document root cannot be removed".to_string());
    };
    match resolve_mut(document, parent)? {
        Json::Object(members) => members
            .shift_remove(last)
            .ok_or_else(|| format!("\"{last}\" does not exist")),
        Json::Array(items) => {
            let index = array_index(last)?;
            if index < items.len() {
                Ok(items.remove(index))
            } else {
                Err(format!("index {index} is outside the array"))
            }
        }
        _ => Err(format!("\"{last}\" does not exist")),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn apply(document: Json, patch: Json) -> Result<Json, String> {
        apply_patch(&document, patch.as_array().unwrap())
    }

    #[test]
    fn add_sets_members_and_inserts_into_arrays() {
        assert_eq!(
            apply(
                json!({"a": 1}),
                json!([{"op": "add", "path": "/b", "value": 2}])
            )
            .unwrap(),
            json!({"a": 1, "b": 2})
        );
        assert_eq!(
            apply(
                json!({"a": 1}),
                json!([{"op": "add", "path": "/a", "value": null}])
            )
            .unwrap(),
            json!({"a": null})
        );
        assert_eq!(
            apply(
                json!([1, 3]),
                json!([{"op": "add", "path": "/1", "value": 2}])
            )
            .unwrap(),
            json!([1, 2, 3])
        );
        assert_eq!(
            apply(json!([1]), json!([{"op": "add", "path": "/-", "value": 2}])).unwrap(),
            json!([1, 2])
        );
        assert_eq!(
            apply(json!([1]), json!([{"op": "add", "path": "/1", "value": 2}])).unwrap(),
            json!([1, 2])
        );
        assert!(apply(json!([1]), json!([{"op": "add", "path": "/2", "value": 2}])).is_err());
        assert!(
            apply(
                json!({}),
                json!([{"op": "add", "path": "/a/b", "value": 2}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!({"a": 1}),
                json!([{"op": "add", "path": "/a/b", "value": 2}])
            )
            .is_err()
        );
    }

    #[test]
    fn remove_and_replace_need_an_existing_target() {
        assert_eq!(
            apply(
                json!({"a": 1, "b": 2, "c": 3}),
                json!([{"op": "remove", "path": "/b"}])
            )
            .unwrap(),
            json!({"a": 1, "c": 3})
        );
        assert_eq!(
            apply(json!([1, 2, 3]), json!([{"op": "remove", "path": "/1"}])).unwrap(),
            json!([1, 3])
        );
        assert!(apply(json!({}), json!([{"op": "remove", "path": "/a"}])).is_err());
        assert!(apply(json!([1]), json!([{"op": "remove", "path": "/1"}])).is_err());
        assert!(apply(json!([1]), json!([{"op": "remove", "path": "/-"}])).is_err());
        assert!(apply(json!({}), json!([{"op": "remove", "path": ""}])).is_err());
        assert_eq!(
            apply(
                json!({"a": 1}),
                json!([{"op": "replace", "path": "/a", "value": [2]}])
            )
            .unwrap(),
            json!({"a": [2]})
        );
        assert!(
            apply(
                json!({}),
                json!([{"op": "replace", "path": "/a", "value": 1}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!([1]),
                json!([{"op": "replace", "path": "/1", "value": 1}])
            )
            .is_err()
        );
    }

    #[test]
    fn removing_a_member_keeps_the_order_of_the_rest() {
        let patched = apply(
            json!({"a": 1, "b": 2, "c": 3, "d": 4}),
            json!([{"op": "remove", "path": "/a"}]),
        )
        .unwrap();
        let names: Vec<&String> = patched.as_object().unwrap().keys().collect();
        assert_eq!(names, ["b", "c", "d"]);
    }

    #[test]
    fn move_and_copy_follow_add_semantics_at_the_target() {
        assert_eq!(
            apply(
                json!({"a": {"x": 1}}),
                json!([{"op": "move", "from": "/a/x", "path": "/y"}])
            )
            .unwrap(),
            json!({"a": {}, "y": 1})
        );
        assert_eq!(
            apply(
                json!({"a": [1, 2]}),
                json!([{"op": "copy", "from": "/a", "path": "/b"}])
            )
            .unwrap(),
            json!({"a": [1, 2], "b": [1, 2]})
        );
        // A move onto itself changes nothing, but the source must exist.
        assert_eq!(
            apply(
                json!({"a": 1}),
                json!([{"op": "move", "from": "/a", "path": "/a"}])
            )
            .unwrap(),
            json!({"a": 1})
        );
        assert!(
            apply(
                json!({}),
                json!([{"op": "move", "from": "/a", "path": "/a"}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!({}),
                json!([{"op": "copy", "from": "/a", "path": "/b"}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!({"a": [[1]]}),
                json!([{"op": "move", "from": "/a/0", "path": "/a/0/0"}])
            )
            .is_err()
        );
    }

    #[test]
    fn test_compares_numbers_by_value() {
        assert!(
            apply(
                json!({"a": 1}),
                json!([{"op": "test", "path": "/a", "value": 1.0}])
            )
            .is_ok()
        );
        assert!(
            apply(
                json!({"a": 1}),
                json!([{"op": "test", "path": "/a", "value": 2}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!({}),
                json!([{"op": "test", "path": "/a", "value": null}])
            )
            .is_err()
        );
        assert!(
            apply(
                json!({"a": null}),
                json!([{"op": "test", "path": "/a", "value": null}])
            )
            .is_ok()
        );
        assert!(
            apply(
                json!([1]),
                json!([{"op": "test", "path": "", "value": [1]}])
            )
            .is_ok()
        );
    }

    #[test]
    fn a_failed_patch_leaves_the_document_untouched() {
        let document = json!({"a": 1});
        let patch = json!([
            {"op": "add", "path": "/b", "value": 2},
            {"op": "remove", "path": "/missing"},
        ]);
        assert!(apply_patch(&document, patch.as_array().unwrap()).is_err());
        assert_eq!(document, json!({"a": 1}));
    }

    #[test]
    fn malformed_operations_are_rejected_before_any_is_applied() {
        for patch in [
            json!([1]),
            json!([{"path": "/a"}]),
            json!([{"op": "add", "value": 1}]),
            json!([{"op": "add", "path": "/a"}]),
            json!([{"op": "add", "path": "a", "value": 1}]),
            json!([{"op": "add", "path": 1, "value": 1}]),
            json!([{"op": "move", "path": "/a"}]),
            json!([{"op": "merge", "path": "/a", "value": 1}]),
        ] {
            assert!(apply(json!({"a": 1}), patch.clone()).is_err(), "{patch}");
        }
    }

    #[test]
    fn array_indexes_have_no_leading_zeros() {
        assert!(apply(json!([1, 2]), json!([{"op": "remove", "path": "/01"}])).is_err());
        assert!(apply(json!([1, 2]), json!([{"op": "remove", "path": "/+1"}])).is_err());
        assert!(apply(json!([1, 2]), json!([{"op": "remove", "path": "/0"}])).is_ok());
    }

    #[test]
    fn pointer_escapes_decode_in_order() {
        assert_eq!(
            parse_pointer("/a~1b/~0key/~01").unwrap(),
            ["a/b", "~key", "~1"]
        );
        assert_eq!(parse_pointer("/").unwrap(), [""]);
        assert_eq!(parse_pointer("").unwrap(), Vec::<String>::new());
    }
}
