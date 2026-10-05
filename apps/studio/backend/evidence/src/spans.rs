//! Read access to the loosely typed members of one span.

use std::sync::LazyLock;

use crate::json::{JsonObject, get};

static EMPTY: LazyLock<JsonObject> = LazyLock::new(JsonObject::new);

/// A span's attributes. Anything other than an object reads as none.
pub fn attributes(span: &JsonObject) -> &JsonObject {
    get(span, "attributes_json").as_object().unwrap_or(&EMPTY)
}

/// A span's resource attributes. Anything other than an object reads as none.
pub fn resource(span: &JsonObject) -> &JsonObject {
    get(span, "resource_attributes_json")
        .as_object()
        .unwrap_or(&EMPTY)
}
