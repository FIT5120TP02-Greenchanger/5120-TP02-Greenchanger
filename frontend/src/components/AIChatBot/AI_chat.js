export async function getResponse() {
    const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ingredients: ingredientsArr})
    });
    
    if(!res.ok) {
        throw new Error("API req failed");
    }

    const data = await res.json();
    return data.recipe;